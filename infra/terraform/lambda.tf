data "archive_file" "notifier" {
  type        = "zip"
  source_file = "${path.module}/lambda/notifier/handler.py"
  output_path = "${path.module}/lambda/notifier/handler.zip"
}

resource "aws_iam_role" "notifier" {
  name = "${var.lambda_function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "notifier_logs" {
  role       = aws_iam_role.notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Scoped to exactly this table's stream, not a wildcard grant.
resource "aws_iam_role_policy" "notifier_stream" {
  name = "${var.lambda_function_name}-stream-read"
  role = aws_iam_role.notifier.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetRecords",
        "dynamodb:GetShardIterator",
        "dynamodb:DescribeStream",
        "dynamodb:ListStreams",
      ]
      Resource = aws_dynamodb_table.resume_status.stream_arn
    }]
  })
}

resource "aws_lambda_function" "notifier" {
  function_name    = var.lambda_function_name
  role             = aws_iam_role.notifier.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = 30
  filename         = data.archive_file.notifier.output_path
  source_code_hash = data.archive_file.notifier.output_base64sha256
}

resource "aws_lambda_event_source_mapping" "notifier_stream" {
  event_source_arn  = aws_dynamodb_table.resume_status.stream_arn
  function_name     = aws_lambda_function.notifier.arn
  starting_position = "LATEST"
  batch_size        = 10
}
