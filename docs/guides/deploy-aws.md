# Deploy to AWS

The same Terraform modules that run against the emulator build AWS. Two environments are
provided, `aws-dev` (a cheaper copy: two zones, one NAT gateway, single-AZ database, no WAF) and
`aws-prod` (three zones, NAT per zone, Multi-AZ database, cache failover, WAF, deletion
protection, a year of logs).

```text
Internet -> ALB (HTTPS, optional WAF)
              /api/*, /docs, /openapi.json, /livez, /readyz -> ECS Fargate: api
              /*                                            -> ECS Fargate: web
SQS jobs (+ DLQ) -> ECS Fargate: worker (subprocess sandbox)
api, worker -> RDS PostgreSQL 16, ElastiCache Valkey, S3 (SSE-KMS), SQS, Secrets Manager
```

Modules (`infra/terraform/modules`): `network`, `kms`, `secrets`, `database`, `cache`, `queue`,
`storage`, `ecr`, `edge`, `service`, `observability`, composed by `deployment`.

## Prerequisites

- An AWS account and credentials in your shell; Terraform 1.10 or newer; Docker with buildx; the AWS CLI
- A domain: a Route53 hosted zone (the certificate and DNS record are created for you), or an issued ACM certificate you point the host name at yourself

## Deploy

```bash
cp infra/terraform/envs/aws-dev/terraform.tfvars.example infra/terraform/envs/aws-dev/terraform.tfvars
# edit name_prefix, hostname, route53_zone_id (or certificate_arn), alarm_email
make aws-plan   ENV=aws-dev      # optional: see what will be created
make aws-deploy ENV=aws-dev      # registries, ARM64 images, infrastructure, rollout
```

`make aws-deploy` applies the registries first, builds and pushes the `api` and `web` images for
`linux/arm64`, applies everything else with that image tag, and waits for the services. State
is local unless you copy `backend.tf.example` to `backend.tf` first (recommended: an encrypted,
versioned S3 bucket with locking).

Then create the administrator, **before** sharing the URL (the first account becomes the
instance administrator):

```bash
make aws-cli ENV=aws-dev ARGS="user create --email you@example.com --name 'You' --admin"
```

The one-off task prints a temporary password; sign in and change it.

## What the deployment sets

`APP_ENV=production` with everything `production_problems()` demands: random secrets from
Secrets Manager, `COOKIE_SECURE=true`, explicit `CORS_ORIGINS`, `STORAGE_BACKEND=s3`,
`QUEUE_BACKEND=sqs`, no emulator endpoint, `ALLOW_PRIVATE_GIT_HOSTS=false`,
`SANDBOX_BACKEND=subprocess`, `FORWARDED_ALLOW_IPS` set to the VPC range, and
`DATABASE_SECRET_ARN` so the database password is read from the RDS-managed secret for each new
connection. Add environment variables with `extra_environment`; use a model with `llm_provider`,
`llm_model` and `llm_api_key_secret_arn`.

## About the sandbox on Fargate

Fargate has no Docker daemon, so tests run in the resource-limited subprocess backend: CPU,
address-space, process, file and time limits, a scrubbed environment and a network guard for
Python. It is a guard for honest suites, not a boundary against malicious native code
([ADR 0004](../architecture/adr/0004-sandbox-backends.md)). The worker's security group allows
HTTPS only (AWS endpoints and git hosts); keep it that way. Where you need a hard boundary, run
the worker on EC2 or EKS with the Docker backend and a rootless or remote engine.

## Operating it

- Dashboard: the `codeagent-<env>` CloudWatch dashboard (also in the outputs). Alarms for the load balancer, target health, latency, CPU and memory of every service, the job backlog and dead letters, the database and the cache go to the SNS topic (`alarm_email` subscribes an address).
- `make aws-migrate ENV=...` runs migrations as a one-off task (the API also migrates on boot).
- Scale the worker with `worker_max_count`; the API and web scale on CPU.
- Teardown: `terraform destroy` in the environment. `aws-prod` has deletion protection on; turn it off deliberately first.

Costs: `aws-dev` is dominated by the NAT gateway, RDS and ElastiCache. Use `aws-dev` for trials and destroy it afterwards.
