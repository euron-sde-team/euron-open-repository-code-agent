variable "endpoint" {
  description = "Emulator endpoint. http://localhost:4619 from the host, http://floci:4566 inside compose."
  type        = string
  default     = "http://localhost:4619"
}

variable "name_prefix" {
  description = "Must match S3_KMS_KEY_ID (alias/<name_prefix>), S3_BUCKET (<name_prefix>-repositories) and SQS_QUEUE_URL (<name_prefix>-jobs) in deploy/compose/compose.floci.yaml."
  type        = string
  default     = "codeagent-local"
}
