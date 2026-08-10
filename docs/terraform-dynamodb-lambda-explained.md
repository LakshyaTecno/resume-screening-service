# Terraform + DynamoDB Streams + Lambda, explained

Notes on `infra/terraform/`. Verified with `terraform init`, `terraform
validate`, and `terraform fmt` earlier in this project (all passed) — no
real `terraform apply` has been run, since that needs real AWS credentials
and creates real, billable resources.

## Terraform's core idea

Same declarative pattern as Helm, different target: a `.tf` file declares
"this AWS resource should exist with these properties," and `terraform
apply` makes real AWS API calls until reality matches.

**Real difference from Kubernetes/ArgoCD**: Terraform does **not**
continuously watch and self-heal. It only reconciles the moment someone
runs `apply`. Manual changes in the AWS Console sit there unnoticed until
the next `plan`/`apply` — the opposite of ArgoCD's `selfHeal: true`.

## `providers.tf`

```hcl
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}
provider "aws" {
  region = var.aws_region
}
```
Declares which provider plugins this config needs — confirmed live when
`terraform init` printed `Installing hashicorp/aws v5.100.0...`. `aws`
talks to AWS's API; `archive` is a small utility used later to zip a file.

## `variables.tf`

Terraform's input parameters — the same role as Helm's `values.yaml`,
different tool. `table_name` defaults to `"resume-processing-status"`,
which has to *manually* match `dynamodbTableName` in the Helm chart's
`values.yaml` and `app/config.py`'s default. Three tools, three places,
nothing automatically keeps them in sync — a real footgun to remember.

## `dynamodb.tf` — the table + the "Streams" half

```hcl
resource "aws_dynamodb_table" "resume_status" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "candidate_id"
  attribute { name = "candidate_id", type = "S" }
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
}
```
`resource "<type>" "<local_name>"` — `resume_status` is how other blocks
refer back to this (`aws_dynamodb_table.resume_status.stream_arn` gets
reused twice below), Terraform's version of Helm's `include` cross-refs.
`PAY_PER_REQUEST` = billed per actual read/write, sensible for
unpredictable/spiky traffic. `hash_key = "candidate_id"` is the same
partition key from the very first architecture diagram, now real
infrastructure. **`stream_enabled` + `stream_view_type` is the entire
"Streams" half of "DynamoDB Streams + Lambda"** — turning it on makes
DynamoDB emit a running log of every insert/update/delete; `NEW_AND_OLD_IMAGES`
means each record carries both the before and after state.

## `lambda.tf` — IAM, the function, and the wire between them

```hcl
data "archive_file" "notifier" {
  type        = "zip"
  source_file = "${path.module}/lambda/notifier/handler.py"
  output_path = "${path.module}/lambda/notifier/handler.zip"
}
```
A `data` block, not `resource` — "something computed/read," not "something
owned." Zips `handler.py` automatically as part of `apply` instead of a
manual pre-build step.

```hcl
resource "aws_iam_role" "notifier" {
  assume_role_policy = jsonencode({
    Statement = [{ Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
```
A role isn't useful by existing alone — something has to be *allowed to use
it*. This means only the AWS Lambda service itself may act as this role.

```hcl
resource "aws_iam_role_policy" "notifier_stream" {
  policy = jsonencode({
    Statement = [{
      Action   = ["dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:DescribeStream", "dynamodb:ListStreams"]
      Resource = aws_dynamodb_table.resume_status.stream_arn
    }]
  })
}
```
Four permissions, scoped to this one table's stream — not `Resource = "*"`.
The "IAM roles scoped tightly to one queue/bucket/table" principle from the
very first AWS-services conversation, now real code.

```hcl
resource "aws_lambda_function" "notifier" {
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.notifier.output_path
  source_code_hash = data.archive_file.notifier.output_base64sha256
}

resource "aws_lambda_event_source_mapping" "notifier_stream" {
  event_source_arn  = aws_dynamodb_table.resume_status.stream_arn
  function_name     = aws_lambda_function.notifier.arn
  starting_position = "LATEST"
  batch_size        = 10
}
```
`handler = "handler.handler"` = "in `handler.py`, call the function named
`handler()`." `source_code_hash` is how Terraform knows whether to actually
redeploy the Lambda — edit the file, the hash changes. **The
`aws_lambda_event_source_mapping` is the actual wire** connecting the
stream to the Lambda. `batch_size = 10` — one invocation can carry up to 10
stream records at once, which is exactly why `handler.py` loops over
`event["Records"]` instead of assuming a single item.

## `outputs.tf`

Prints real generated values (ARNs, names) after `apply`, so a human can
grab them without digging through the AWS Console — the Terraform
equivalent of a Helm chart's install notes.

## `lambda/notifier/handler.py`

```python
def handler(event, context):
    for record in event.get("Records", []):
        if record.get("eventName") not in ("INSERT", "MODIFY"):
            continue
        item = _deserialize(record.get("dynamodb", {}).get("NewImage"))
        if item.get("status") != "ai-processed":
            continue
        # notify downstream (stubbed - real delivery is out of scope)
```
`_deserialize` exists because DynamoDB's raw stream format wraps every
value in a type tag (`{"S": "ai-processed"}`) instead of a plain value.
Filters specifically for the `ai-processed` transition, logs, and stops —
real notification delivery is an intentional stub, since that piece is
"existing, unchanged" per the original architecture diagram. A genuine,
working reference implementation of the pattern, not a claim that this
repo owns production notifications.
