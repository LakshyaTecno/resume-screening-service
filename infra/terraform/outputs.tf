output "table_name" {
  value = aws_dynamodb_table.resume_status.name
}

output "table_stream_arn" {
  value = aws_dynamodb_table.resume_status.stream_arn
}

output "notifier_function_name" {
  value = aws_lambda_function.notifier.function_name
}
