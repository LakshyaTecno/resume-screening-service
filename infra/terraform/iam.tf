# Permissions app/worker.py actually needs - covers every AWS call it
# makes, nothing more:
#   sqs.receive_message / delete_message / (implicit) get_queue_attributes
#   s3.get_object
#   dynamodb.Table(...).update_item  (see _mark_status)
#
# A standalone policy document, not a full role + trust policy - which IAM
# identity actually assumes this depends on how the worker gets deployed
# (e.g. IRSA on a real EKS cluster), and that's out of scope here same as
# the rest of the cluster itself.
resource "aws_iam_policy" "worker_permissions" {
  name        = "resume-worker-permissions"
  description = "Everything app/worker.py needs: consume the SQS queue, read uploaded PDFs from S3, write processing status to DynamoDB."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.resume_uploaded.arn
      },
      {
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${var.resume_uploads_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = "dynamodb:UpdateItem"
        Resource = aws_dynamodb_table.resume_status.arn
      },
    ]
  })
}
