output "table_name" {
  value = aws_dynamodb_table.resume_status.name
}

output "table_stream_arn" {
  value = aws_dynamodb_table.resume_status.stream_arn
}

output "notifier_function_name" {
  value = aws_lambda_function.notifier.function_name
}

output "sqs_queue_url" {
  description = "Set this as SQS_QUEUE_URL (app/config.py / Helm values.yaml's config.sqsQueueUrl)."
  value       = aws_sqs_queue.resume_uploaded.url
}

output "worker_iam_policy_arn" {
  description = "Attach this to whatever IAM identity actually runs app/worker.py (an IRSA role, an instance profile, etc.)."
  value       = aws_iam_policy.worker_permissions.arn
}
