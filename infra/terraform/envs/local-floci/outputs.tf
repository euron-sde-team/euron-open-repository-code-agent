output "kms_key_alias" {
  description = "S3_KMS_KEY_ID for the local stack."
  value       = module.kms.alias_name
}

output "kms_key_id" {
  description = "Id of the key behind the alias."
  value       = module.kms.key_id
}

output "jobs_queue_url" {
  description = "SQS_QUEUE_URL for the local stack (the emulator reports its own host name)."
  value       = module.queue.queue_url
}

output "jobs_dlq_url" {
  description = "Dead-letter queue for messages that crashed the worker repeatedly."
  value       = module.queue.dlq_url
}

output "app_secret_arn" {
  description = "Secret holding the generated application secrets (not read locally)."
  value       = module.secrets.secret_arn
}

output "repositories_bucket" {
  description = "S3_BUCKET for the local stack."
  value       = module.storage.bucket
}
