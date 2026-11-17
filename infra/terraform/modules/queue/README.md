# `queue` module

The jobs queue and its dead-letter queue, encrypted with the deployment key.

- `<name_prefix>-jobs`: one message per job (index a snapshot, run a task, run tests, apply a patch), carrying ids only. The worker long-polls it, re-reads the row from Postgres and does the work. A duplicate message is harmless: a finished job is skipped.
- `<name_prefix>-jobs-dlq`: receives a message after `max_receive_count` (3) receives, which means the worker crashed on it three times. It is alarmed (see the `observability` module); jobs that merely failed are recorded on their rows in the database, not here.

The visibility timeout (1020 seconds) is the worker's `JOB_TIMEOUT_S` (900) plus a margin of 120, and the worker extends it while a job runs. A queue policy denies non-TLS requests unless `enforce_tls = false` (the local emulator).

## Inputs

| Name                         | Description                                                                               | Type     | Default  |
| ---------------------------- | ----------------------------------------------------------------------------------------- | -------- | -------- |
| `name_prefix`                | Prefix for every resource name. Queues are <name_prefix>-jobs and <name_prefix>-jobs-dlq. | `string` | required |
| `kms_key_arn`                | CMK for server-side encryption. Null uses SQS-managed encryption.                         | `string` | `null`   |
| `visibility_timeout_seconds` | How long a received message stays hidden.                                                 | `number` | `120`    |
| `message_retention_seconds`  | How long an undelivered message is kept.                                                  | `number` | `345600` |
| `max_receive_count`          | Receives before a message moves to the dead-letter queue.                                 | `number` | `3`      |
| `enforce_tls`                | Deny requests that do not use TLS with a queue policy.                                    | `bool`   | `true`   |

## Outputs

| Name         | Description                                    |
| ------------ | ---------------------------------------------- |
| `queue_url`  | SQS_QUEUE_URL for the API and the worker.      |
| `queue_arn`  | Webhook queue ARN, for IAM policies.           |
| `queue_name` | Webhook queue name, for CloudWatch alarms.     |
| `dlq_url`    | Dead-letter queue URL.                         |
| `dlq_arn`    | Dead-letter queue ARN.                         |
| `dlq_name`   | Dead-letter queue name, for CloudWatch alarms. |
