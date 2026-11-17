# `storage` module

The repository bucket `<name_prefix>-repositories`: uploaded archives, each repository's working mirror (`mirror.tar.gz` with its `.git`) and full test logs.

- Private (all four public-access blocks), owner-enforced, encrypted with the deployment key (SSE-KMS with a bucket key), versioned (`enable_versioning`, on everywhere except the local emulator), TLS-only (a bucket policy denies plain HTTP unless `enforce_tls = false`, which only the local emulator needs).
- Keys are grouped by workspace, so deleting a workspace removes its prefix.
- Lifecycle: noncurrent versions expire after `noncurrent_version_days` (30) and incomplete multipart uploads after 7 days. Current objects never expire: a mirror is the repository's working copy, and deleting a workspace or a repository removes its prefix.

## Inputs

| Name                      | Description                            | Type     | Default  |
| ------------------------- | -------------------------------------- | -------- | -------- |
| `name_prefix`             | Prefix for the bucket name.            | `string` | required |
| `kms_key_arn`             | CMK that encrypts every object.        | `string` | required |
| `enforce_tls`             | Deny non-TLS requests.                 | `bool`   | `true`   |
| `enable_versioning`       | Keep previous object versions.         | `bool`   | `true`   |
| `force_destroy`           | Let destroy delete a non-empty bucket. | `bool`   | `false`  |
| `noncurrent_version_days` | Days old versions are kept.            | `number` | `30`     |

## Outputs

| Name         | Description                             |
| ------------ | --------------------------------------- |
| `bucket`     | `S3_BUCKET` for the API and the worker. |
| `bucket_arn` | Bucket ARN, for IAM policies.           |
