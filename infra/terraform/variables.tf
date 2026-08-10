variable "aws_region" {
  description = "AWS region for the DynamoDB table and Lambda function."
  type        = string
  default     = "us-east-1"
}

variable "table_name" {
  description = "DynamoDB table name - must match app/config.py's dynamodb_table_name (DYNAMODB_TABLE_NAME env var) that app/worker.py writes to."
  type        = string
  default     = "resume-processing-status"
}

variable "lambda_function_name" {
  description = "Name of the DynamoDB Streams notifier Lambda."
  type        = string
  default     = "resume-status-notifier"
}
