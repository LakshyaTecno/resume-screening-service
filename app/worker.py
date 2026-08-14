"""SQS-driven ingestion worker.

Consumes `resume-uploaded` events published directly to SQS, downloads the
source PDF from S3, and reuses the existing HTTP-upload pipeline
(`candidate_service.create_candidate_from_pdf`) to parse, store, and embed
the resume. Reports status back to DynamoDB, which feeds the existing
(unowned by this service) DynamoDB-stream notification loop.

Run with: python -m app.worker
"""

import json
import logging
from datetime import datetime, timezone

import boto3

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


def _mark_status(candidate_id: str, status: str) -> None:
    """Write the processing status Service A's stream-and-notify loop watches for.

    Keyed by the external candidate_id from the SQS event, not this service's
    internal Postgres primary key — downstream consumers of the notification
    loop only know about the id Service A assigned at upload time.
    """
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
    bucket = body["s3_bucket"]
    key = body["s3_key"]

    logger.info("Processing candidate_id=%s from s3://%s/%s", candidate_id, bucket, key)
    obj = s3.get_object(Bucket=bucket, Key=key)
    file_bytes = obj["Body"].read()

    db = SessionLocal()
    try:
        candidate_service.create_candidate_from_pdf(db, file_bytes)
    finally:
        db.close()

    _mark_status(candidate_id, "ai-processed")
    logger.info("candidate_id=%s marked ai-processed", candidate_id)


def run() -> None:
    if not settings.sqs_queue_url:
        raise RuntimeError("SQS_QUEUE_URL is not configured")

    logger.info("Worker started, polling %s", settings.sqs_queue_url)
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
                _process_message(body)
                sqs.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=receipt_handle)
            except ResumeContentError as exc:
                # Not retryable - bad input. Drop it rather than retry forever.
                logger.warning("Discarding unprocessable message: %s", exc)
                sqs.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=receipt_handle)
            except (ResumeParserUnavailableError, VectorIndexingError) as exc:
                # Transient infra failure - leave the message for SQS's visibility-timeout
                # retry (and eventual redrive to a dead-letter queue, if one is configured).
                logger.error("Transient failure, will retry: %s", exc)
            except Exception:
                logger.exception("Unexpected error processing message %s", message.get("MessageId"))


if __name__ == "__main__":
    run()
