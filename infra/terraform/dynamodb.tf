# Status table app/worker.py writes `status: ai-processed` to, keyed by the
# external candidate_id from the upstream upload event - not this service's
# internal Postgres primary key (see app/worker.py's _mark_status docstring).
# The stream this enables feeds the Lambda notifier defined in lambda.tf.
resource "aws_dynamodb_table" "resume_status" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "candidate_id"

  attribute {
    name = "candidate_id"
    type = "S"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }
}
