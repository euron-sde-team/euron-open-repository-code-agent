variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "vpc_id" {
  description = "VPC for the load balancer."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets, one per AZ."
  type        = list(string)
}

variable "hostname" {
  description = "The one public host name of the deployment, for example codeagent.example.com. The web app is served at / and the API under /v1, so the browser and the API share an origin."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the host name. When set, the certificate is validated and the alias record is created automatically."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "Existing ACM certificate covering the host name. Null requests a new one."
  type        = string
  default     = null
}

variable "access_logs_bucket" {
  description = "Bucket for ALB access logs. Null disables them."
  type        = string
  default     = null
}

variable "idle_timeout_seconds" {
  description = "How long the load balancer waits on an idle connection. Must exceed the longest request: extraction with a hosted model can take as long as LLM_TIMEOUT_S (60 seconds)."
  type        = number
  default     = 120
}

variable "enable_waf" {
  description = "Put a WAF (AWS managed rules plus a per-IP rate limit) in front of the load balancer."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Requests per 5 minutes from one IP before the WAF blocks it. Assistant backends call from a few addresses, so this is generous; per-key limits are enforced by the API itself."
  type        = number
  default     = 20000
}

variable "deletion_protection" {
  description = "Protect the load balancer from deletion."
  type        = bool
  default     = false
}
