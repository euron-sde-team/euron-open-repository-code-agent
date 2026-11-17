variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
  default     = "codeagent-prod"
}

variable "hostname" {
  description = "Public host name: the dashboard is served at / and the API under /api/v1 on this one host."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the host name: the certificate is validated and the DNS record created for you. Null: bring an issued certificate_arn and point the host name at the load balancer yourself."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "Existing, issued ACM certificate for the host name. Required without route53_zone_id."
  type        = string
  default     = null
}

variable "product_name" {
  description = "Name shown in the dashboard."
  type        = string
  default     = "Euron CodeAgent"
}

variable "image_tag" {
  description = "Image tag to deploy (make aws-deploy passes the git commit)."
  type        = string
  default     = "latest"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.r7g.large"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.r7g.large"
}

variable "alarm_email" {
  description = "Address that receives alarm notifications."
  type        = string
  default     = null
}

variable "allow_signup" {
  description = "Let anyone create an account from the sign-in page. Off: owners add people from the dashboard."
  type        = bool
  default     = false
}

variable "llm_provider" {
  description = "Answers and the agent planner: none (the offline local engine), openai (OpenAI-compatible) or ollama."
  type        = string
  default     = "none"
}

variable "llm_model" {
  description = "Model name for llm_provider."
  type        = string
  default     = ""
}

variable "llm_base_url" {
  description = "OpenAI-compatible endpoint."
  type        = string
  default     = "https://api.openai.com/v1"
}

variable "llm_api_key_secret_arn" {
  description = "ECS valueFrom reference to the provider key (<secret arn>:<json key>::)."
  type        = string
  default     = null
}
