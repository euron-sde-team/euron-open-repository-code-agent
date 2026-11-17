# ADR 0008: Slow work is queued on SQS with ids only, and a reaper resends what was lost

## Status

Accepted.

## Context

Indexing, agent runs, test runs and applying patches take seconds to minutes. They must not block requests, must survive a crashed worker, and must not run twice with different results.

## Decision

The API enqueues `{type, workspace_id, target_id}` after committing the row. The worker long-polls, runs jobs with bounded concurrency, extends each message's visibility while the job runs, deletes the message when the job has recorded its outcome and leaves it to reappear when the job asks to be retried; after three receives SQS moves it to a dead-letter queue with an alarm. Handlers re-read the row and are no-ops for finished work. A reaper, elected through Valkey, resends work stuck in `queued`, `running` or `indexing` past `STALE_JOB_MINUTES` (failing it after three attempts) and skips resending while the queue has a backlog, so it does not amplify one.

## Consequences

- At-least-once delivery means handlers must be idempotent; every handler starts by checking state under a row lock.
- A job that is slower than the visibility extension interval can be delivered twice; the lock and state check make the second one a no-op.

## Alternatives considered

A database-backed queue (fine at small scale, but the AWS deployment already has SQS and its dead-lettering); Celery or RQ (another broker and process model for four job types)..
