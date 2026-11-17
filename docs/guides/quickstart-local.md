# Quickstart: run it locally

Everything runs on your machine with no cloud account and no API key.

## Prerequisites

- Docker with Compose v2 (Docker Desktop, Colima or Docker Engine), about 6 GB of free memory
- `make`, `openssl`
- For development on the code itself: Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node.js 22 with pnpm 9 (`corepack enable`)

## Start the stack

```bash
make up
```

The first run builds three images and applies Terraform to the Floci emulator, which takes a
few minutes. It starts:

| Service  | Port          | Role                                                                                                    |
| -------- | ------------- | ------------------------------------------------------------------------------------------------------- |
| web      | 3190          | The web app                                                                                             |
| api      | 8190          | REST and server-sent events; the reference is at `/docs`                                                |
| worker   | (9100 inside) | Indexing, agent runs, test runs, applying patches; mounts the Docker socket to start sandbox containers |
| postgres | 5459          | PostgreSQL 16 with pgvector and pg_trgm                                                                 |
| valkey   | 6419          | Caches, rate limits, locks                                                                              |
| floci    | 4619          | The AWS emulator (S3, SQS, KMS, Secrets Manager), provisioned by Terraform                              |

`make env` (run by `make up`) writes `deploy/compose/.env` with random, local-only secrets.

## Load the demo

```bash
make demo
```

It creates the workspace **Northwind Engineering** with four people (owner, maintainer,
developer, viewer), uploads three sample repositories (a Python billing library with one
deliberately failing test, a Go rate limiter and a TypeScript checkout module), has the worker
index them, answers a handful of questions, runs the tests in the sandbox, and has the agent
work on five tasks (a fixed test and a helper waiting for review, a rename that was approved and
applied, a helper that was rejected, and a request the offline planner cannot do, which failed).
The command prints the logins and a CI API key. Sign in at http://localhost:3190 with
`priya.raman@example.com` and the printed password.

## Try it

1. **Browse.** Repositories, then `ledgerkit`, then Browse code. Click a line number; shift-click
   another to select a range. Open the outline and pick `apply_discount` to see its callers and tests.
2. **Search.** Search for `discount` (symbols), then `Decimal` (text, try a regular expression),
   then "limit requests per client" (by meaning).
3. **Ask.** "Where is the tax for an invoice calculated?" Each `[n]` chip opens the cited lines.
4. **Review a change.** Tasks, then "Fix the failing pricing test". Read the diff, the tests
   before and after, and approve it (task #4 needs someone other than its requester, because the
   workspace requires independent review).
5. **Ask for a change.** New task, template "Add a helper": `add \`clamp\` to ledgerkit/pricing.py`.
Watch the trace, then review and apply it to a branch, and export the `.patch`.
6. **Run tests.** Test runs, then Run tests. The log and per-test results come from the sandbox.

## Use your own repository

Repositories, then Connect repository: upload a `.zip` or `.tar.gz`, or give an HTTPS clone
URL (public repositories need no credentials). To connect a git server on this machine, set
`CODEAGENT_ALLOW_PRIVATE_GIT_HOSTS=true` in `deploy/compose/.env`. Set a test command in the
repository's settings (the default is `python -m pytest -q`).

## Use a model

Set `CODEAGENT_LLM_PROVIDER` (`ollama` or `openai`) and `CODEAGENT_LLM_MODEL` in
`deploy/compose/.env` (see [configuration.md](configuration.md)), then `make down up`. Answers
and open-ended tasks then use the model; the offline engines remain the default for tests.

## Stop

```bash
make down     # stops the stack and deletes its volumes (the Terraform provider cache is kept)
```

## Develop without the full stack

```bash
scripts/test-deps.sh                      # Postgres, Valkey and Floci on their ports
cd apps/api && uv sync && MIGRATE_ON_BOOT=true uv run uvicorn codeagent.main:create_app --factory --port 8190
pnpm install && pnpm --filter @codeagent/web dev
```

With the default settings the API keeps files in `data/files` and runs jobs in-process, so no
worker is needed to index and search.
