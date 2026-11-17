variable "name_prefix" {
  description = "Prefix for the bucket name. The bucket is <name_prefix>-repositories."
  type        = string
}

variable "kms_key_arn" {
  description = "CMK that encrypts every object (SSE-KMS with an S3 bucket key)."
  type        = string
}

variable "enforce_tls" {
  description = "Deny requests that do not use TLS with a bucket policy. Off only for the local emulator, which speaks plain HTTP."
  type        = bool
  default     = true
}

variable "enable_versioning" {
  description = "Keep previous versions of overwritten objects (a mirror overwritten by a bad sync can be restored). On in every AWS environment; off only for the local emulator."
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = "Let terraform destroy delete a bucket that still holds objects (development environments only)."
  type        = bool
  default     = false
}

variable "noncurrent_version_days" {
  description = "Days an overwritten or deleted version of a repository mirror is kept."
  type        = number
  default     = 30
}
