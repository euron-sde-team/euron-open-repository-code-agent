# `kms` module

One customer-managed KMS key (annual rotation) plus the alias `alias/<name_prefix>`. CodeAgent uses it two ways:

- **Through S3.** Every object in the repository bucket is written with this key (SSE-KMS); the API and worker roles may use it for `s3.<region>.amazonaws.com` only. The application passes it as `S3_KMS_KEY_ID`.
- **At rest, through AWS services.** The jobs queue and its dead-letter queue, the bucket, RDS storage, the Valkey cache, Secrets Manager, ECR, CloudWatch logs and the alarm topic.

Usage is granted per role by IAM (the account root delegates), scoped by `kms:ViaService`. Only CloudWatch is named in the key policy: Logs for this account's log groups, and Alarms so alarm notifications can reach the encrypted SNS topic (an AWS-managed key cannot be used for that).

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The alias is alias/<name_prefix>. | `string` | required |
| `deletion_window_in_days` | Waiting period before a scheduled key deletion completes. | `number` | `30` |
| `admin_principal_arns` | IAM principals allowed to administer (not use) the key. Empty = account root only, which delegates to IAM policies. | `list(string)` | `[]` |
| `rotation_period_in_days` | Days between automatic rotations of the key material. Null leaves the period to the service (365 on AWS). | `number` | `365` |

## Outputs

| Name | Description |
|---|---|
| `key_arn` | KMS key ARN. |
| `key_id` | KMS key id. |
| `alias_name` | Alias, usable as KMS_KEY_ID. |
