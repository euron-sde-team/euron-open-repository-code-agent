# CodeAgent API and worker

FastAPI service for Euron CodeAgent, plus the worker that indexes repositories, runs the
agent, runs tests in the sandbox and applies approved patches. Both run from one image
with different commands.

```bash
uv sync                                   # Python 3.12 and every dependency
uv run uvicorn codeagent.main:create_app --factory --reload --port 8190
uv run python -m codeagent.worker         # the job worker (QUEUE_BACKEND=sqs)
uv run codeagent --help                   # CLI: migrations, users, demo data, reindex, OpenAPI
uv run pytest tests/unit                  # unit tests, no services needed
```

## Layout

```text
src/codeagent/
├── main.py           app factory: middleware, routers, lifespan
├── worker.py         SQS consumer: bounded concurrency, heartbeats, graceful shutdown
├── cli.py            typer CLI
├── core/             config, logging, errors, request context, security, rate limits, metrics
├── db/               engine, sessions, declarative base, column types, migrations runner
├── models/           SQLAlchemy models, one module per aggregate
├── schemas/          Pydantic request and response models
├── repositories/     the only code that touches the database
├── services/         business rules, transactions, cache invalidation, job orchestration
├── api/              routes and dependencies (caller, workspace role, rate limits)
├── codeintel/        languages, search terms, symbols, chunks, highlighting, archives
├── ai/               embeddings, chat clients, answerers, prompts, citations
├── agent/            planners, skills, edit blocks, diffs, the run loop
├── sandbox/          Docker and subprocess backends, JUnit parsing, network guard
├── integrations/     AWS clients, storage, queue, git
└── demo/             demo seed and the bundled demo repositories
```

## The rules

| Layer | May import | Must not |
| --- | --- | --- |
| `api/routes` | schemas, services, `api/deps` | touch a session, a repository or Redis directly |
| `services` | repositories, `codeintel`, `ai`, `agent`, `sandbox`, `integrations`, `core` | import FastAPI |
| `repositories` | models, `db` | commit, call another service, or skip the `workspace_id` filter |
| `codeintel`, `ai`, `agent` (pure parts) | `core` | do database I/O; they are unit tested on their own |

**Workspace isolation.** Every repository method that reads workspace data takes
`workspace_id` as a required argument. The `WorkspaceAccess` dependency in `api/deps.py`
resolves the caller's role first and answers 404 to non-members.

**Transactions.** A service method that writes opens and commits its own transaction.
Routes never commit.

**Errors.** Raise the typed errors in `core/errors.py`. Every response uses one envelope:
`{"error": {"code", "message", "request_id", "details?"}}`.

**Nothing changes a repository without approval.** Only `services/review.py` (an approved
patch) and `services/indexing.py` (an import or a sync the maintainer started) write a
repository mirror.

## Tests

| Suite | Needs | Run |
| --- | --- | --- |
| `tests/unit` | nothing | `uv run pytest tests/unit` |
| `tests/integration` | Postgres with pgvector, Valkey, the AWS emulator (Docker for the sandbox tests) | `make test-integration` from the repo root |
