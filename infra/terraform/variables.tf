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

variable "sqs_queue_name" {
  description = "SQS queue name - must match app/config.py's sqs_queue_url (SQS_QUEUE_URL env var) that app/worker.py long-polls."
  type        = string
  default     = "resume-uploaded"
}

variable "resume_uploads_bucket_arn" {
  description = "ARN of the S3 bucket resumes are uploaded to. In a real deployment this is Service A's infrastructure, referenced not created here - default below is a bucket created by hand (aws s3api create-bucket, not Terraform) purely to test the worker's IAM policy end-to-end."
  type        = string
  default     = "arn:aws:s3:::resume-uploads-208618103838"
}
