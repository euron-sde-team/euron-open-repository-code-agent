# The repository bucket: uploaded archives, the working mirror of every repository
# (mirror.tar.gz, with its .git) and full test logs, under
#
#   workspaces/<workspace id>/repositories/<repository id>/...
#   workspaces/<workspace id>/test-runs/<run id>/log.txt
#
# Private, encrypted with the deployment key, versioned (a mirror that is overwritten by a
# bad sync can be restored), TLS-only. Only the API and the worker task roles may use it
# (the deployment module grants them access to this bucket and nothing else).
locals {
  bucket = "${var.name_prefix}-repositories"
}

resource "aws_s3_bucket" "this" {
  #checkov:skip=CKV_AWS_144:Cross-region replication is a deployment decision; the mirror can be rebuilt from the git host or the uploaded archive.
  #checkov:skip=CKV2_AWS_62:No event notifications are needed: the worker polls the database, not the bucket.
  #checkov:skip=CKV_AWS_18:Access logging needs a second bucket; object access is recorded in CloudTrail data events where enabled.
  bucket        = local.bucket
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  count = var.enforce_tls ? 1 : 0
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  count  = var.enforce_tls ? 1 : 0
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.tls_only[0].json
}
