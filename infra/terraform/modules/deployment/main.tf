# -----------------------------------------------------------------------------
# One complete CodeAgent deployment: network, keys, data, queue, cache and services.
#
#   https://<hostname>/            dashboard (web)
#   https://<hostname>/api/v1/... API; reference at /docs; /metrics is not public
#   worker                         indexing, agent runs, test runs and patch application
#                                  from SQS, and the reaper on a schedule; no inbound
#                                  traffic. Tests run in its resource-limited subprocess
#                                  sandbox (Fargate has no Docker daemon)
#
# The dashboard and the API share one host name and one origin, so the session cookie is
# first-party and the API needs no CORS exceptions. envs/aws-dev and envs/aws-prod call
# this module with different sizes and safety switches; everything else is identical by
# construction.
#
# First sign-in: the first account created becomes the instance administrator, and the
# first-run page in the dashboard will create it for whoever opens it first. Create the
# administrator right after the first deploy (`make aws-cli ARGS="user create ..."`),
# before sharing the URL.
# -----------------------------------------------------------------------------
data "aws_region" "current" {}

locals {
  region   = data.aws_region.current.region
  site_url = "https://${var.hostname}"
  urls = {
    web  = local.site_url
    api  = "${local.site_url}/api/v1"
    docs = "${local.site_url}/docs"
  }
  images = { for k, url in module.ecr.repository_urls : k => "${url}:${var.image_tag}" }
}

# --- Foundation --------------------------------------------------------------

module "network" {
  source                     = "../network"
  name_prefix                = var.name_prefix
  cidr_block                 = var.vpc_cidr
  az_count                   = var.az_count
  single_nat_gateway         = var.single_nat_gateway
  enable_interface_endpoints = var.enable_interface_endpoints
  flow_log_retention_days    = var.flow_log_retention_days
  logs_kms_key_arn           = module.kms.key_arn
}

module "kms" {
  source                  = "../kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = var.kms_deletion_window_days
  admin_principal_arns    = var.kms_admin_principal_arns
}

module "secrets" {
  source                  = "../secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = var.secret_recovery_window_days
}

module "database" {
  source                = "../database"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  subnet_ids            = module.network.private_subnet_ids
  kms_key_arn           = module.kms.key_arn
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  multi_az              = var.db_multi_az
  backup_retention_days = var.db_backup_retention_days
  deletion_protection   = var.deletion_protection
  skip_final_snapshot   = !var.deletion_protection
  monitoring_interval   = var.db_monitoring_interval
}

module "queue" {
  source      = "../queue"
  name_prefix = var.name_prefix
  kms_key_arn = module.kms.key_arn
}

module "storage" {
  source        = "../storage"
  name_prefix   = var.name_prefix
  kms_key_arn   = module.kms.key_arn
  force_destroy = !var.deletion_protection
}

module "cache" {
  source                  = "../cache"
  name_prefix             = var.name_prefix
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  kms_key_arn             = module.kms.key_arn
  node_type               = var.cache_node_type
  replicas                = var.cache_replicas
  apply_immediately       = !var.deletion_protection
  recovery_window_in_days = var.secret_recovery_window_days
}

module "ecr" {
  source       = "../ecr"
  name_prefix  = var.name_prefix
  repositories = ["api", "web"]
  kms_key_arn  = module.kms.key_arn
  force_delete = !var.deletion_protection
}

# --- Edge --------------------------------------------------------------------

module "edge" {
  source               = "../edge"
  name_prefix          = var.name_prefix
  vpc_id               = module.network.vpc_id
  public_subnet_ids    = module.network.public_subnet_ids
  hostname             = var.hostname
  route53_zone_id      = var.route53_zone_id
  certificate_arn      = var.certificate_arn
  access_logs_bucket   = var.alb_access_logs_bucket
  idle_timeout_seconds = var.alb_idle_timeout_seconds
  enable_waf           = var.enable_waf
  waf_rate_limit       = var.waf_rate_limit
  deletion_protection  = var.deletion_protection
}

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix
  setting {
    name  = "containerInsights"
    value = "enhanced"
  }
}

# --- Shared application configuration ----------------------------------------

locals {
  # Everything Settings.production_problems() insists on is set here: secrets from Secrets
  # Manager (and distinct), secure cookies, explicit CORS origins, S3 storage, the SQS queue,
  # no emulator endpoint and no git URLs that resolve to private addresses.
  app_environment = merge({
    APP_ENV       = "production"
    TZ            = "UTC"
    LOG_FORMAT    = "json"
    PRODUCT_NAME  = var.product_name
    AWS_REGION    = local.region
    CORS_ORIGINS  = local.site_url
    WEB_URL       = local.site_url
    API_URL       = local.site_url
    COOKIE_SECURE = "true"
    ALLOW_SIGNUP  = tostring(var.allow_signup)
    QUEUE_BACKEND = "sqs"
    SQS_QUEUE_URL = module.queue.queue_url
    # Archives, mirrors and test logs: the private, KMS-encrypted bucket.
    STORAGE_BACKEND         = "s3"
    S3_BUCKET               = module.storage.bucket
    S3_KMS_KEY_ID           = module.kms.key_arn
    ALLOW_PRIVATE_GIT_HOSTS = "false"
    # Fargate has no Docker daemon: test runs use the resource-limited subprocess sandbox.
    SANDBOX_BACKEND = "subprocess"
    # No password in the environment: the app reads it from the RDS-managed secret for
    # each new connection, so a rotation needs no redeploy.
    DATABASE_URL        = "postgresql+asyncpg://${module.database.master_username}@${module.database.address}:${module.database.port}/${module.database.database_name}?ssl=require"
    DATABASE_SECRET_ARN = module.database.master_user_secret_arn
    # Trust X-Forwarded-For only from inside the VPC (the load balancer), so the per-address
    # sign-in limit sees the real client and not whatever a client claims to be.
    FORWARDED_ALLOW_IPS = module.network.vpc_cidr_block
    # The offline code-hash embedder: nothing is downloaded at runtime.
    EMBEDDINGS_PROVIDER = "local"
    LLM_PROVIDER        = var.llm_provider
    LLM_MODEL           = var.llm_model
    LLM_BASE_URL        = var.llm_base_url
    OLLAMA_URL          = var.ollama_url
  }, var.extra_environment)

  app_secrets = concat(
    [for k in module.secrets.keys : { name = k, valueFrom = "${module.secrets.secret_arn}:${k}::" }],
    [{ name = "REDIS_URL", valueFrom = "${module.cache.url_secret_arn}:REDIS_URL::" }],
    var.llm_api_key_secret_arn == null ? [] : [{ name = "LLM_API_KEY", valueFrom = var.llm_api_key_secret_arn }],
  )
}

# --- Task roles (least privilege, one per application) ------------------------

data "aws_iam_policy_document" "common" {
  statement {
    sid       = "DatabasePassword"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [module.database.master_user_secret_arn]
  }
  statement {
    sid       = "ReadSecretsViaSecretsManager"
    actions   = ["kms:Decrypt"]
    resources = [module.kms.key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${local.region}.amazonaws.com"]
    }
  }
}

# Anything that enqueues a job writes to an encrypted queue.
data "aws_iam_policy_document" "enqueue" {
  statement {
    sid       = "EnqueueJobs"
    actions   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
    resources = [module.queue.queue_arn]
  }
  statement {
    sid       = "EncryptedQueue"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [module.kms.key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["sqs.${local.region}.amazonaws.com"]
    }
  }
}

# Archives, mirrors and test logs live in one bucket; objects are written and read with
# the deployment key (SSE-KMS), so the roles need the key for S3 only.
data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [module.storage.bucket_arn]
  }
  statement {
    sid       = "ReadWriteObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${module.storage.bucket_arn}/*"]
  }
  statement {
    sid       = "EncryptedBucket"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [module.kms.key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
  }
}

# The API stores uploaded archives, serves files and logs, and enqueues jobs. It never
# runs repository code.
data "aws_iam_policy_document" "api" {
  source_policy_documents = [
    data.aws_iam_policy_document.common.json,
    data.aws_iam_policy_document.enqueue.json,
    data.aws_iam_policy_document.bucket.json,
  ]
}

# The worker consumes the queue (and re-enqueues what the reaper finds stuck), reads and
# writes mirrors and logs, and is the only component that runs repository code.
data "aws_iam_policy_document" "worker" {
  source_policy_documents = [
    data.aws_iam_policy_document.common.json,
    data.aws_iam_policy_document.enqueue.json,
    data.aws_iam_policy_document.bucket.json,
  ]
  statement {
    sid       = "ConsumeJobs"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"]
    resources = [module.queue.queue_arn]
  }
}

# One-off commands (migrate, user create, reindex) touch the database and may enqueue jobs.
data "aws_iam_policy_document" "cli" {
  source_policy_documents = [
    data.aws_iam_policy_document.common.json,
    data.aws_iam_policy_document.enqueue.json,
    data.aws_iam_policy_document.bucket.json,
  ]
}

locals {
  python_health = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=3)\""]
  worker_health = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:${local.worker_metrics_port}/metrics', timeout=3)\""]
  # Same value as WORKER_METRICS_PORT in the compose stack, so dashboards read one number.
  worker_metrics_port = 9170
}

# --- Services ----------------------------------------------------------------

# The API owns the schema: it migrates under an advisory lock on boot, so any number of
# tasks can start together and the migrations still run once.
module "api" {
  source                   = "../service"
  name_prefix              = var.name_prefix
  name                     = "api"
  image                    = local.images.api
  environment              = merge(local.app_environment, { MIGRATE_ON_BOOT = tostring(var.migrate_on_boot) })
  secrets                  = local.app_secrets
  cluster_arn              = aws_ecs_cluster.this.arn
  vpc_id                   = module.network.vpc_id
  subnet_ids               = module.network.private_subnet_ids
  listener_arn             = module.edge.https_listener_arn
  lb_security_group_id     = module.edge.security_group_id
  listener_priority        = 100
  path_patterns            = ["/api/*", "/docs", "/openapi.json", "/livez", "/readyz"]
  health_check_path        = "/livez"
  connect_to_database      = true
  db_security_group_id     = module.database.security_group_id
  db_port                  = module.database.port
  connect_to_cache         = true
  cache_security_group_id  = module.cache.security_group_id
  kms_key_arn              = module.kms.key_arn
  has_task_policy          = true
  task_policy_json         = data.aws_iam_policy_document.api.json
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  min_count                = var.api_min_count
  max_count                = var.api_max_count
  log_retention_days       = var.log_retention_days
  logs_kms_key_arn         = module.kms.key_arn
  container_health_command = local.python_health
}

module "worker" {
  source      = "../service"
  name_prefix = var.name_prefix
  name        = "worker"
  image       = local.images.api
  command     = ["python", "-m", "codeagent.worker"]
  environment = merge(local.app_environment, {
    MIGRATE_ON_BOOT     = "false"
    WORKER_CONCURRENCY  = tostring(var.worker_concurrency)
    WORKER_METRICS_PORT = tostring(local.worker_metrics_port)
  })
  container_health_command = local.worker_health
  # The worker stops receiving on SIGTERM and gives running jobs two minutes to finish and
  # hand their work back; the stop timeout (the Fargate maximum) leaves room for that.
  stop_timeout            = 120
  secrets                 = local.app_secrets
  attach_to_load_balancer = false
  cluster_arn             = aws_ecs_cluster.this.arn
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  connect_to_database     = true
  db_security_group_id    = module.database.security_group_id
  db_port                 = module.database.port
  connect_to_cache        = true
  cache_security_group_id = module.cache.security_group_id
  kms_key_arn             = module.kms.key_arn
  has_task_policy         = true
  task_policy_json        = data.aws_iam_policy_document.worker.json
  cpu                     = var.worker_cpu
  memory                  = var.worker_memory
  min_count               = var.worker_min_count
  max_count               = var.worker_max_count
  log_retention_days      = var.log_retention_days
  logs_kms_key_arn        = module.kms.key_arn
}

# One-off tasks on the API image: migrations, accounts, a reindex (make aws-cli).
# Nothing here needs a terminal: pass every argument on the command line.
module "cli" {
  source                  = "../service"
  name_prefix             = var.name_prefix
  name                    = "cli"
  image                   = local.images.api
  command                 = ["codeagent", "--help"]
  environment             = merge(local.app_environment, { MIGRATE_ON_BOOT = "false" })
  secrets                 = local.app_secrets
  create_service          = false
  cluster_arn             = aws_ecs_cluster.this.arn
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  connect_to_database     = true
  db_security_group_id    = module.database.security_group_id
  db_port                 = module.database.port
  connect_to_cache        = true
  cache_security_group_id = module.cache.security_group_id
  kms_key_arn             = module.kms.key_arn
  has_task_policy         = true
  task_policy_json        = data.aws_iam_policy_document.cli.json
  cpu                     = 512
  memory                  = 1024
  log_retention_days      = var.log_retention_days
  logs_kms_key_arn        = module.kms.key_arn
}

# The dashboard: a Next.js server that reads API_URL and PRODUCT_NAME when it starts
# (/env.js), so one image serves every environment. It claims every path the API does not.
module "web" {
  source               = "../service"
  name_prefix          = var.name_prefix
  name                 = "web"
  image                = local.images.web
  environment          = { API_URL = local.site_url, PRODUCT_NAME = var.product_name, PORT = "8080", HOSTNAME = "0.0.0.0" }
  cluster_arn          = aws_ecs_cluster.this.arn
  vpc_id               = module.network.vpc_id
  subnet_ids           = module.network.private_subnet_ids
  listener_arn         = module.edge.https_listener_arn
  lb_security_group_id = module.edge.security_group_id
  listener_priority    = 900
  path_patterns        = ["/*"]
  health_check_path    = "/env.js"
  kms_key_arn          = module.kms.key_arn
  cpu                  = var.web_cpu
  memory               = var.web_memory
  min_count            = var.web_min_count
  max_count            = var.web_max_count
  log_retention_days   = var.log_retention_days
  logs_kms_key_arn     = module.kms.key_arn
}

# --- Observability -----------------------------------------------------------

module "observability" {
  source                     = "../observability"
  name_prefix                = var.name_prefix
  kms_key_arn                = module.kms.key_arn
  alarm_email                = var.alarm_email
  alb_arn_suffix             = module.edge.arn_suffix
  ecs_cluster_name           = aws_ecs_cluster.this.name
  db_instance_identifier     = module.database.instance_identifier
  db_max_connections         = var.db_max_connections
  cache_replication_group_id = module.cache.replication_group_id
  cache_node_count           = module.cache.node_count
  queue_name                 = module.queue.queue_name
  dlq_name                   = module.queue.dlq_name
  services = {
    api    = module.api.service_name
    worker = module.worker.service_name
    web    = module.web.service_name
  }
  target_groups = {
    api = module.api.target_group_arn_suffix
    web = module.web.target_group_arn_suffix
  }
}
