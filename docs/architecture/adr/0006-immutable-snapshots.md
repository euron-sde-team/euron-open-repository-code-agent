# ADR 0006: An index is an immutable snapshot swapped in atomically

## Status

Accepted.

## Context

Re-indexing a repository takes seconds to minutes. Readers (search, answers, an agent run) must never see a half-built index, and a task must keep reading the code it started from even if the repository is synced meanwhile.

## Decision

A snapshot indexes one commit and is written in one transaction (bulk inserts with application-generated ids), then marked `ready` while the repository's `current_snapshot_id` moves to it in the same transaction. Everything reads through the current snapshot. A task records its base snapshot and commit, and the agent run reads that one. Re-delivered jobs are no-ops for ready snapshots, a retry of a failed one deletes its partial rows, and only the newest `SNAPSHOT_RETENTION` snapshots are kept. Patches copy old and new file content, so pruning never breaks a review.

## Consequences

- Storage for up to three copies of an index per repository, bounded by retention.
- An index is rebuilt from scratch on each sync; incremental indexing keyed on file hashes is on the roadmap (the SHA-256 per file is already stored).

## Alternatives considered

Updating the index in place (readers see partial states and deletions); a snapshot per file (complicates every query)..
