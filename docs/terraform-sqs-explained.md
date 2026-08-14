# SQS + worker IAM, explained

Notes on `infra/terraform/sqs.tf` and `iam.tf` — the last piece from the
original project audit. Verified with `terraform fmt`/`terraform validate`
only, same as the DynamoDB/Lambda Terraform before it — no real
`terraform apply`, since that needs real AWS credentials.

## Why plain SQS, not SNS → SQS

Earlier diagrams and docs in this project (including the published
architecture artifact linked from the README) show SNS in front of the
queue. That got corrected here, on purpose: **SNS's entire value is fanning
one event out to multiple independent consumers.** If a second team later
wants to react to the same `resume-uploaded` event — say, an analytics
pipeline — they'd subscribe their own queue to the same topic without
touching Service A's code at all. That's a real, valuable pattern. It's
just not *this* project's situation — there has only ever been one
consumer, this worker. Adding SNS anyway would mean an extra hop, an extra
piece of infrastructure to reason about, in exchange for a decoupling
benefit nothing here actually uses. `app/worker.py`'s docstring used to say
"fanned out via SNS -> SQS" — fixed to "published directly to SQS" to
match. The code itself never actually cared either way; it only ever calls
`sqs.receive_message()`, with no idea what put the message there.

## `sqs.tf`

```hcl
resource "aws_sqs_queue" "resume_uploaded" {
  name = var.sqs_queue_name
  visibility_timeout_seconds = 120
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.resume_uploaded_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue" "resume_uploaded_dlq" {
  name = "${var.sqs_queue_name}-dlq"
}
```

**`visibility_timeout_seconds = 120` isn't an arbitrary number** — it has
to match `app/worker.py`'s own hardcoded `VisibilityTimeout=120` in its
`receive_message()` call. Visibility timeout is how long SQS hides a
message from other consumers after it's been picked up, giving the worker
time to actually finish processing before the message could be handed out
again. Terraform and the Python code agreeing on this value is a real,
manual responsibility — nothing enforces it automatically, and it's worth
remembering as the kind of cross-file consistency this project keeps
running into (the same DynamoDB table name has to match across `.tf`,
`values.yaml`, and `app/config.py` too).

**The dead-letter queue (`redrive_policy` + `maxReceiveCount = 5`)**:
`app/worker.py`'s own error handling already distinguishes two failure
kinds — a `ResumeContentError` (bad PDF) gets deleted immediately, not
retried; a transient failure (Ollama down, Pinecone down) gets left on the
queue for a retry. The DLQ exists for the case where a "retryable" failure
keeps failing anyway — after 5 attempts, SQS moves the message here
instead of retrying forever, so a permanently broken message doesn't sit
in an infinite retry loop.

## `iam.tf`

```hcl
resource "aws_iam_policy" "worker_permissions" {
  policy = jsonencode({
    Statement = [
      { Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.resume_uploaded.arn },
      { Action = "s3:GetObject", Resource = "${var.resume_uploads_bucket_arn}/*" },
      { Action = "dynamodb:UpdateItem", Resource = aws_dynamodb_table.resume_status.arn },
    ]
  })
}
```

This closes a gap that's existed silently since `app/worker.py` was first
written: **no IAM permissions were ever defined for the worker at all.**
`lambda.tf`'s existing IAM role is for the *notifier* Lambda — a
completely different identity, reacting to the DynamoDB stream, not
consuming SQS.

Every permission here maps to one specific line in `app/worker.py`:
- `sqs:ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes` → `run()`'s
  polling loop
- `s3:GetObject` → `_process_message()`'s `s3.get_object(Bucket=bucket, Key=key)`
- `dynamodb:UpdateItem` → `_mark_status()`'s `table.update_item(...)`

Nothing broader. `Resource = aws_dynamodb_table.resume_status.arn` reuses
the *existing* table resource from `dynamodb.tf` rather than redeclaring
it — same "reference, don't duplicate" pattern as
`aws_dynamodb_table.resume_status.stream_arn` being reused in `lambda.tf`.

**Why a policy, not a role**: a role needs a trust policy — a statement
saying *who* is allowed to assume it. That depends entirely on how the
worker actually gets deployed (IAM Roles for Service Accounts on a real
EKS cluster, an EC2 instance profile, etc.), and provisioning that cluster
is out of scope here, same as everywhere else this project draws that
line. `worker_permissions` is a standalone, attachable policy document —
whatever identity ends up running the worker attaches it.

## `resume_uploads_bucket_arn` — a placeholder, on purpose

```hcl
variable "resume_uploads_bucket_arn" {
  default = "arn:aws:s3:::CHANGE_ME"
}
```

The S3 bucket resumes get uploaded to is Service A's infrastructure, per
the original architecture — not created here, only referenced so the IAM
policy can grant read access to it. Same `CHANGE_ME` convention already
used in `argocd/application.yaml`'s `repoURL` — a clear signal that a real
value has to be supplied before this could actually be applied.
