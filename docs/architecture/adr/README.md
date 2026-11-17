# Architecture Decision Records

Each record captures one significant decision: the context that forced it, what was decided,
what it costs, and what else was considered. Records are immutable once accepted; a change of
mind is a new record that supersedes the old one.

| ADR                                                              | Title                                                                                                 | Status   |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | -------- |
| [0001](0001-postgres-pgvector-and-trigram-for-the-code-index.md) | Postgres with pgvector and pg_trgm holds the whole code index                                         | Accepted |
| [0002](0002-offline-local-engines-by-default.md)                 | Every AI capability has a deterministic offline implementation, with models behind the same interface | Accepted |
| [0003](0003-verified-citations.md)                               | Citations are validated against the sources an answer was given                                       | Accepted |
| [0004](0004-sandbox-backends.md)                                 | Tests run in a Docker container where a daemon exists, and in a limited subprocess where it does not  | Accepted |
| [0005](0005-patches-are-reviewed-proposals.md)                   | Agents only propose patches; a maintainer approves, and applying makes a branch in the mirror         | Accepted |
| [0006](0006-immutable-snapshots.md)                              | An index is an immutable snapshot swapped in atomically                                               | Accepted |
| [0007](0007-floci-for-local-aws.md)                              | Develop against an AWS emulator (Floci), provisioned by the production Terraform                      | Accepted |
| [0008](0008-jobs-through-sqs-with-a-reaper.md)                   | Slow work is queued on SQS with ids only, and a reaper resends what was lost                          | Accepted |
| [0009](0009-sessions-as-signed-cookies-with-origin-checks.md)    | Web sessions are signed cookies protected by origin checks; scripts use API keys                      | Accepted |

## Template

```markdown
# ADR NNNN: <decision in one line>

## Status

Proposed | Accepted | Superseded by NNNN

## Context

What forces are at play, and why a decision is needed now.

## Decision

What we will do, concretely.

## Consequences

What gets easier, what gets harder, what we now have to maintain.

## Alternatives considered

What else was possible, and why it lost.
```
