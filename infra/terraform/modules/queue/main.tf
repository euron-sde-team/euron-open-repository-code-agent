# The jobs queue: indexing, agent runs, test runs and patch application, one message each,
# carrying only ids. The worker re-reads the rows in Postgres, so a duplicated or stale
# message is harmless (a job that is already finished is skipped).
#
# A message whose processing crashes the worker becomes visible again after the visibility
# timeout; after max_receive_count receives SQS moves it to the dead-letter queue, where
# it waits for an operator to inspect it. Nothing is lost meanwhile: the work is a row in
# the database, and the reaper resends the ones whose message vanished.
locals {
  managed_sse = var.kms_key_arn == null
  queues = {
    jobs = aws_sqs_queue.jobs.arn
    dlq  = aws_sqs_queue.dlq.arn
  }
}

resource "aws_sqs_queue" "dlq" {
  name                              = "${var.name_prefix}-jobs-dlq"
  message_retention_seconds         = 1209600
  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = local.managed_sse ? null : 300
  sqs_managed_sse_enabled           = local.managed_sse ? true : null
}

resource "aws_sqs_queue" "jobs" {
  name                              = "${var.name_prefix}-jobs"
  visibility_timeout_seconds        = var.visibility_timeout_seconds
  message_retention_seconds         = var.message_retention_seconds
  receive_wait_time_seconds         = 20
  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = local.managed_sse ? null : 300
  sqs_managed_sse_enabled           = local.managed_sse ? true : null
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.jobs.arn]
  })
}

# Job ids are not secrets, but nothing about this queue should travel in clear text.
data "aws_iam_policy_document" "tls_only" {
  for_each = var.enforce_tls ? local.queues : {}
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [each.value]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "tls_only" {
  for_each  = data.aws_iam_policy_document.tls_only
  queue_url = each.key == "dlq" ? aws_sqs_queue.dlq.id : aws_sqs_queue.jobs.id
  policy    = each.value.json
}
