variable "name_prefix" {
  description = "Prefix for every resource name. Queues are <name_prefix>-jobs and <name_prefix>-jobs-dlq."
  type        = string
}

variable "kms_key_arn" {
  description = "CMK for server-side encryption. Null uses SQS-managed encryption."
  type        = string
  default     = null
}

variable "visibility_timeout_seconds" {
  description = "How long a received message stays hidden; must cover the worker's job timeout plus its 120 second margin (JOB_TIMEOUT_S 900 gives 1020), which is what a crashed worker holds a message for."
  type        = number
  default     = 1020
}

variable "message_retention_seconds" {
  description = "How long an undelivered message is kept (4 days by default). The job rows in Postgres are the durable record."
  type        = number
  default     = 345600
}

variable "max_receive_count" {
  description = "Receives before a message moves to the dead-letter queue."
  type        = number
  default     = 3
}

variable "enforce_tls" {
  description = "Deny requests that do not use TLS with a queue policy. Off only for the local emulator, which speaks plain HTTP."
  type        = bool
  default     = true
}
