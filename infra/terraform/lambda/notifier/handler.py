"""Reference implementation of the DynamoDB Streams -> Lambda notification
pattern this project's architecture relies on.

In the real integration this loop is owned by another team (documented as
"existing, unchanged" in the service's architecture diagram) - this is a
working, portfolio-grade example of the same pattern: a candidate's
processing status flips to ai-processed, the stream carries that change, and
this function reacts to it.
"""

import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _deserialize(image: dict) -> dict:
    """Unwrap DynamoDB's {"S": "..."}-style attribute-value wrapper."""
    result = {}
    for key, typed_value in image.items():
        ((_, value),) = typed_value.items()
        result[key] = value
    return result


def handler(event, context):
    processed = 0
    for record in event.get("Records", []):
        if record.get("eventName") not in ("INSERT", "MODIFY"):
            continue

        new_image = record.get("dynamodb", {}).get("NewImage")
        if not new_image:
            continue

        item = _deserialize(new_image)
        if item.get("status") != "ai-processed":
            continue

        candidate_id = item.get("candidate_id")
        logger.info("candidate_id=%s finished processing - notifying downstream", candidate_id)
        processed += 1

        # Real notification delivery (email/SMS/webhook to the recruiter-facing
        # product) is out of scope here and owned by the existing pipeline this
        # stands in for - this is where that call would go.

    return {"processed": processed}
