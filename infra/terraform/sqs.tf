# The queue app/worker.py long-polls. Deliberately plain SQS, no SNS in
# front of it - SNS's whole value is fanning one event out to *multiple*
# consumers, and this project only ever has one (this worker). Whatever
# publishes here (Service A's "Lambda A", per the architecture) sends
# directly to this queue.
resource "aws_sqs_queue" "resume_uploaded" {
  name = var.sqs_queue_name

  # Must match app/worker.py's hardcoded VisibilityTimeout=120 in its
  # receive_message call - nothing enforces these staying in sync
  # automatically, so a change to one needs the other updated by hand.
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.resume_uploaded_dlq.arn
    maxReceiveCount     = 5
  })
}

# Messages that fail processing 5 times land here instead of retrying
# forever. app/worker.py's own error handling already distinguishes
# retryable failures (left on the queue) from non-retryable ones (deleted
# immediately) - this catches the case where a "retryable" failure keeps
# failing anyway.
resource "aws_sqs_queue" "resume_uploaded_dlq" {
  name                      = "${var.sqs_queue_name}-dlq"
  message_retention_seconds = 1209600 # 14 days
}
