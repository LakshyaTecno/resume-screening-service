"""SQS-driven ingestion worker.

Consumer half of the async upload path this service owns end-to-end:
POST /candidates/upload (app/routers/candidates.py) creates a placeholder
Candidate row and publishes the `resume-uploaded` message this worker
consumes (see app/services/ingestion.py for the producer side). This
worker downloads the source PDF from S3, parses it, and updates the
existing placeholder row in place - it does not insert a new row, since
the row's id was already handed to the client for polling at upload time.
Reports status back to DynamoDB, which feeds the existing (unowned by this
service) DynamoDB-stream notification loop.

Run with: python -m app.worker
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import boto3
from prometheus_client import Counter, Histogram, start_http_server

from app.config import get_settings
from app.database import SessionLocal
from app.exceptions import ResumeContentError, ResumeParserUnavailableError, VectorIndexingError
from app.services import candidate_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("resume-worker")

settings = get_settings()

sqs = boto3.client("sqs", region_name=settings.aws_region)
s3 = boto3.client("s3", region_name=settings.aws_region)
dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)

# One counter per real outcome this worker can have - the labels match the
# exception branches in run()'s try/except exactly, not an idealized list.
MESSAGES_PROCESSED = Counter(
    "resume_worker_messages_processed_total",
    "Messages this worker has finished handling, by outcome.",
    ["outcome"],
)
PROCESSING_DURATION = Histogram(
    "resume_worker_processing_duration_seconds",
    "Time spent in _process_message() per message, regardless of outcome.",
)


def _mark_status(candidate_id: str, status: str) -> None:
    """Write the processing status the downstream DynamoDB-stream notifier
    watches for. Keyed by this service's own Postgres candidate id - the
    same id returned to the client by POST /candidates/upload, since this
    service now owns both the producer and consumer side of the queue."""
    table = dynamodb.Table(settings.dynamodb_table_name)
    table.update_item(
        Key={"candidate_id": candidate_id},
        UpdateExpression="SET #s = :status, updated_at = :updated_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _process_message(body: dict) -> None:
    candidate_id = body["candidate_id"]
    tenant_id = body["tenant_id"]
    bucket = body["s3_bucket"]
    key = body["s3_key"]

    logger.info("Processing candidate_id=%s from s3://%s/%s", candidate_id, bucket, key)
    obj = s3.get_object(Bucket=bucket, Key=key)
    file_bytes = obj["Body"].read()

    db = SessionLocal()
    try:
        candidate_service.process_pending_candidate(
            db, UUID(tenant_id), UUID(candidate_id), file_bytes
        )
    finally:
        db.close()

    _mark_status(candidate_id, "ai-processed")
    logger.info("candidate_id=%s marked ai-processed", candidate_id)


def run() -> None:
    if not settings.sqs_queue_url:
        raise RuntimeError("SQS_QUEUE_URL is not configured")

    start_http_server(settings.worker_metrics_port)
    logger.info(
        "Worker started, polling %s (metrics on :%d)",
        settings.sqs_queue_url,
        settings.worker_metrics_port,
    )
    while True:
        response = sqs.receive_message(
            QueueUrl=settings.sqs_queue_url,
            MaxNumberOfMessages=5,
            WaitTimeSeconds=20,
            VisibilityTimeout=120,
        )
        for message in response.get("Messages", []):
            receipt_handle = message["ReceiptHandle"]
            try:
                body = json.loads(message["Body"])
                with PROCESSING_DURATION.time():
                    _process_message(body)
                sqs.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=receipt_handle)
                MESSAGES_PROCESSED.labels(outcome="success").inc()
            except ResumeContentError as exc:
                # Not retryable - bad input. Drop it rather than retry forever.
                logger.warning("Discarding unprocessable message: %s", exc)
                sqs.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=receipt_handle)
                MESSAGES_PROCESSED.labels(outcome="content_error").inc()
            except (ResumeParserUnavailableError, VectorIndexingError) as exc:
                # Transient infra failure - leave the message for SQS's visibility-timeout
                # retry (and eventual redrive to a dead-letter queue, if one is configured).
                logger.error("Transient failure, will retry: %s", exc)
                MESSAGES_PROCESSED.labels(outcome="transient_error").inc()
            except Exception:
                logger.exception("Unexpected error processing message %s", message.get("MessageId"))
                MESSAGES_PROCESSED.labels(outcome="unexpected_error").inc()


if __name__ == "__main__":
    run()
