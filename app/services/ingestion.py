"""Owns the S3/SQS side of the async resume-upload path: puts the raw PDF
to S3 and publishes the same-shaped `resume-uploaded` message app/worker.py
already consumes. This is the producer half of a pipeline this service now
owns end-to-end - see the upload flow in app/services/candidate_service.py
and the consumer in app/worker.py.
"""

import json
from uuid import UUID

import boto3

from app.config import get_settings

settings = get_settings()

s3 = boto3.client("s3", region_name=settings.aws_region)
sqs = boto3.client("sqs", region_name=settings.aws_region)


def upload_resume_and_enqueue(candidate_id: UUID, tenant_id: UUID, file_bytes: bytes) -> None:
    key = f"uploads/{candidate_id}.pdf"
    s3.put_object(Bucket=settings.s3_bucket_name, Key=key, Body=file_bytes)
    sqs.send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps(
            {
                "candidate_id": str(candidate_id),
                "tenant_id": str(tenant_id),
                "s3_bucket": settings.s3_bucket_name,
                "s3_key": key,
            }
        ),
    )
