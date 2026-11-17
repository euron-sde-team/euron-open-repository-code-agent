output "bucket" {
  description = "S3_BUCKET for the API and the worker."
  value       = aws_s3_bucket.this.bucket
}

output "bucket_arn" {
  description = "Bucket ARN, for IAM policies."
  value       = aws_s3_bucket.this.arn
}
