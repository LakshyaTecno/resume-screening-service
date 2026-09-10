# Resume uploads bucket. Previously created by hand (see variables.tf's
# prior comment) back when an external "Service A" was assumed to own
# uploads - this service now owns the upload endpoint itself
# (app/routers/candidates.py -> app/services/ingestion.py), so it owns
# this bucket too.
resource "aws_s3_bucket" "resume_uploads" {
  bucket = var.resume_uploads_bucket_name
}
