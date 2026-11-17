# ADR 0005: Agents only propose patches; a maintainer approves, and applying makes a branch in the mirror

## Status

Accepted.

## Context

A tool that edits code automatically is only adoptable if teams stay in control of what lands. The agent will sometimes be wrong, and a model can be steered by text in the repository.

## Decision

A task produces a _patch revision_: a unified diff, per-file old and new content, a plan, a rationale, and the test results from before and after. The agent never writes to the repository mirror. A maintainer approves or rejects (with the independent-review option, not the requester), and only an approved patch can be applied; the worker re-checks approval under a row lock, restores the mirror under a repository lock, creates `codeagent/<number>-<slug>` from the base commit, runs `git apply --check` and `--index`, and commits with `Requested-by` and `Approved-by` trailers. CodeAgent never pushes; people take the branch or the `git am` patch out. Retrying creates a new revision and supersedes the old one, so what was reviewed never changes underneath the reviewer.

## Consequences

- One more step between idea and merge than a tool that pushes a pull request. It is the point.
- The mirror grows branches; they are cheap, and deleting the repository removes them.
- A patch can go stale as the repository moves on; the base commit is recorded and a failed apply is reported with the git error and leaves the patch approved so it can be retried.

## Alternatives considered

Opening pull requests on the host directly (needs write credentials, which CodeAgent deliberately does not hold); auto-approving when tests pass (tests passing is evidence, not consent)..
