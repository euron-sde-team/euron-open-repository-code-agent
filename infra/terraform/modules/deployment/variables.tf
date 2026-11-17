variable "name_prefix" {
  description = "Prefix for every resource name; one AWS account can host several deployments."
  type        = string
}

variable "hostname" {
  description = "The public host name, for example codeagent.example.com. The dashboard is served at / and the API under /v1 on this one host."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the host name. When set, the certificate and the DNS record are created automatically."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "Existing, issued ACM certificate for the host name. Null requests one, which only completes when route53_zone_id is set (the HTTPS listener needs an issued certificate)."
  type        = string
  default     = null
}

variable "product_name" {
  description = "Name shown in the dashboard."
  type        = string
  default     = "Euron CodeAgent"
}

variable "image_tag" {
  description = "Image tag deployed for the api and web repositories (the git commit by default)."
  type        = string
}

variable "migrate_on_boot" {
  description = "Run pending migrations when an API task starts (under an advisory lock)."
  type        = bool
  default     = true
}

variable "allow_signup" {
  description = "Let anyone create an account and an organisation from the sign-in page. Off by default: owners add people from the dashboard. The very first account is always allowed."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "VPC address range."
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Availability zones to spread across."
  type        = number
  default     = 2
}

variable "single_nat_gateway" {
  description = "One NAT gateway for all zones (cheaper, less available)."
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Interface VPC endpoints for KMS, Secrets Manager and SQS (keeps that traffic off the NAT)."
  type        = bool
  default     = false
}

variable "flow_log_retention_days" {
  description = "VPC flow log retention."
  type        = number
  default     = 30
}

variable "kms_deletion_window_days" {
  description = "Waiting period before the deployment key can be deleted."
  type        = number
  default     = 30
}

variable "kms_admin_principal_arns" {
  description = "IAM principals allowed to administer the deployment key."
  type        = list(string)
  default     = []
}

variable "secret_recovery_window_days" {
  description = "Secrets Manager recovery window (0 deletes immediately)."
  type        = number
  default     = 7
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "Initial database storage in GiB."
  type        = number
  default     = 30
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling in GiB."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  description = "Standby replica in a second zone."
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  description = "Automated backup retention."
  type        = number
  default     = 7
}

variable "db_monitoring_interval" {
  description = "Enhanced monitoring interval in seconds (0 disables it)."
  type        = number
  default     = 60
}

variable "db_max_connections" {
  description = "Connection ceiling the database alarm measures against (each API, worker and CLI process opens up to 20)."
  type        = number
  default     = 200
}

variable "cache_node_type" {
  description = "ElastiCache node type for Valkey."
  type        = string
  default     = "cache.t4g.small"
}

variable "cache_replicas" {
  description = "Valkey read replicas; one or more enables automatic failover."
  type        = number
  default     = 0
}

variable "deletion_protection" {
  description = "Protect the database, load balancer and registries from deletion."
  type        = bool
  default     = false
}

variable "enable_waf" {
  description = "Put a WAF in front of the load balancer."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Requests per 5 minutes from one IP before the WAF blocks it."
  type        = number
  default     = 20000
}

variable "alb_access_logs_bucket" {
  description = "Bucket for load balancer access logs. Null disables them."
  type        = string
  default     = null
}

variable "alb_idle_timeout_seconds" {
  description = "Load balancer idle timeout; keep it above LLM_TIMEOUT_S (60 seconds) when a hosted extraction model is configured."
  type        = number
  default     = 120
}

variable "api_cpu" {
  description = "API task CPU units."
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "API task memory (MiB); search ranks vectors and highlights files in-process."
  type        = number
  default     = 2048
}

variable "api_min_count" {
  description = "Minimum API tasks."
  type        = number
  default     = 1
}

variable "api_max_count" {
  description = "Maximum API tasks."
  type        = number
  default     = 2
}

variable "worker_cpu" {
  description = "Worker task CPU units (indexing and test runs are CPU bound)."
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Worker task memory (MiB): indexing holds a repository in memory, and each test run gets up to SANDBOX_MEMORY_MB of it."
  type        = number
  default     = 4096
}

variable "worker_concurrency" {
  description = "Jobs a worker task runs at once (WORKER_CONCURRENCY)."
  type        = number
  default     = 2
}

variable "worker_min_count" {
  description = "Minimum worker tasks. The reaper is elected across them, so one is enough; more add job throughput and redundancy."
  type        = number
  default     = 1
}

variable "worker_max_count" {
  description = "Maximum worker tasks."
  type        = number
  default     = 1
}

variable "web_cpu" {
  description = "Web task CPU units."
  type        = number
  default     = 256
}

variable "web_memory" {
  description = "Web task memory (MiB)."
  type        = number
  default     = 512
}

variable "web_min_count" {
  description = "Minimum web tasks."
  type        = number
  default     = 1
}

variable "web_max_count" {
  description = "Maximum web tasks."
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "CloudWatch log retention for every service."
  type        = number
  default     = 30
}

variable "alarm_email" {
  description = "Address that receives alarm notifications. Null: subscribe something else to the topic."
  type        = string
  default     = null
}

variable "llm_provider" {
  description = "Answers and the agent planner: none (the deterministic local engine, fully offline), openai (any OpenAI-compatible endpoint) or ollama."
  type        = string
  default     = "none"
  validation {
    condition     = contains(["none", "openai", "ollama"], var.llm_provider)
    error_message = "llm_provider must be none, openai or ollama."
  }
}

variable "llm_model" {
  description = "Model name for llm_provider (required when a provider is set)."
  type        = string
  default     = ""
  validation {
    condition     = var.llm_provider == "none" || var.llm_model != ""
    error_message = "llm_model is required when llm_provider is openai or ollama."
  }
}

variable "llm_base_url" {
  description = "Base URL of the OpenAI-compatible endpoint."
  type        = string
  default     = "https://api.openai.com/v1"
}

variable "ollama_url" {
  description = "Base URL of an Ollama server reachable from the private subnets (llm_provider = ollama)."
  type        = string
  default     = "http://localhost:11434"
}

variable "llm_api_key_secret_arn" {
  description = "Secret (and JSON key) holding the model provider key, as ECS valueFrom: <arn>:<key>::. Null: no key."
  type        = string
  default     = null
}

variable "extra_environment" {
  description = "Additional environment variables for the API, worker and CLI (see apps/api/src/codeagent/core/config.py)."
  type        = map(string)
  default     = {}
}
