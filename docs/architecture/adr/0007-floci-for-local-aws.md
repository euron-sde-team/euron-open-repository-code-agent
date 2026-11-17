# ADR 0007: Develop against an AWS emulator (Floci), provisioned by the production Terraform

## Status

Accepted.

## Context

In production CodeAgent depends on S3 (archives, mirrors, logs), SQS with a dead-letter queue (jobs), KMS (encryption of both) and Secrets Manager, next to RDS and ElastiCache. Local development that swaps each of these for a different mechanism (a directory, an in-process queue) leaves the paths that matter most in production untested until they reach a real account: S3 multipart and server-side encryption, SQS long polling, visibility timeouts and redrive, and the Terraform itself.

## Decision

- `make up` runs the Floci AWS emulator (`floci/floci:2.3.0`, MIT licence) next to Postgres with pgvector, Valkey and the application images.
- A one-shot Terraform container applies `infra/terraform/envs/local-floci` against the emulator before the API and the worker start. That environment uses the **same** `kms`, `queue`, `storage` and `secrets` modules as production, with only the endpoint and a few emulator switches changed (no TLS-only policies, short deletion windows). The database and cache are compose containers, so the `database`, `cache`, `network`, `edge` and `service` modules are not used locally.
- The API and the worker run with `STORAGE_BACKEND=s3`, `QUEUE_BACKEND=sqs` and `S3_KMS_KEY_ID=alias/codeagent-local`, pointed at the emulator with `AWS_ENDPOINT_URL`. The application has no emulator-specific branches (`integrations/aws.py` builds the same clients for both, with path-style S3 addressing when an endpoint is set).
- Terraform state for the local environment lives in a Docker volume and is wiped with the emulator by `make down`.
- The integration suite provisions its own key, bucket and uniquely named queues on a throwaway emulator (`scripts/test-deps.sh`, ports 5459 to 4619) and runs the real worker path against them.
- `QUEUE_BACKEND=inline` and `STORAGE_BACKEND=local` remain for running the API alone and for most tests; production refuses both.

## Consequences

- The emulator is a dependency to track and its behaviour can differ from AWS in corners; the integration tests pin the behaviour the application relies on, and the real Terraform is also validated, linted and scanned.
- The first `make up` takes minutes while Terraform applies and images build.

## Alternatives considered

Mocking boto3 (tests the mock); localstack (a different licence and a heavier footprint); running everything on real AWS in development (needs an account and costs money)..
