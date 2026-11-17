# Contributing

Thanks for helping improve Euron CodeAgent. This guide covers the workflow, the bar a change
has to clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak, so we can agree
  on the approach before you invest time.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. See
  [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Development setup

Requirements: Docker with Compose v2, Python 3.12 with [uv](https://docs.astral.sh/uv/), and
Node.js 22 with pnpm 9 (`corepack enable`).

```bash
make up          # Postgres (pgvector), Valkey, the AWS emulator (provisioned by Terraform), api, worker, web
make demo        # a demo workspace: three indexed repositories, answers, tasks and patches in every state
make test        # unit tests for the API (pytest) and the web app (Vitest)
```

[docs/guides/quickstart-local.md](docs/guides/quickstart-local.md) walks through the local
stack in detail.

### A faster loop without the full stack

The full stack builds images. For day-to-day work on the API or the web app, run only what you
need on the host:

```bash
scripts/test-deps.sh                                   # Postgres with pgvector (5459), Valkey (6419), Floci (4619)
cd apps/api && uv run uvicorn codeagent.main:create_app --factory --port 8190   # with MIGRATE_ON_BOOT=true
pnpm --filter @codeagent/web dev                       # the web app on http://localhost:3190
```

The API's default settings use the inline job queue and local file storage, so no worker or
emulator is needed to index a repository while you work. Run the worker against the emulator
with `make up` when you change `worker.py`, the queue or a job handler.

## Before you open a pull request

Each of these must pass:

```bash
make lint typecheck test
make test-integration                  # the API against real Postgres, Valkey and the AWS emulator
make e2e                               # when you touched a user flow, the web app or infrastructure
make tf-validate tf-lint tf-security   # when you touched infra/terraform
make sanitize                          # no credentials, account ids or resource ids
```

## Conventions

**Layers (api).** Routes declare the URL, the request and response models and the access
dependency, nothing else. Services hold the business rules, transactions and cache
invalidation. Repositories are the only code that issues SQL. Code intelligence (`codeintel/`),
answers (`ai/`), planners and skills (`agent/`) and the sandbox protocol are pure where they
can be, so they are unit tested without a database.
[docs/architecture/LLD.md](docs/architecture/LLD.md) has the rules for each layer.

**Data stays in its workspace.** Every repository method that reads workspace data takes the
workspace id. The integration suite sweeps every workspace route as an outsider and expects
404 from each, so a new route is covered the moment it is added to the sweep: add it.

**Repository code only runs in the sandbox.** Never execute, import or `exec` anything from an
indexed repository in the API or the worker process. A new feature that needs to run it goes
through `sandbox/` with limits.

**Nothing changes a repository without approval.** Agents propose; a maintainer approves; the
worker re-checks the approval under a row lock before it touches the mirror.

**Offline first.** A feature that uses a model ships a deterministic local implementation and
the model adapters behind the same interface, and its tests run offline.

**Configuration is validated.** A new environment variable is declared in
`apps/api/src/codeagent/core/config.py` and documented in
[docs/guides/configuration.md](docs/guides/configuration.md) in the same PR. Settings that
matter for security are enforced at boot when `APP_ENV=production`.

**Database changes are new migrations.** `uv run alembic revision -m "describe it"` in
`apps/api`. Never edit an applied migration. The embedding width is fixed per deployment, so a
new embedding model is a migration that re-embeds every chunk.

**Errors use the envelope.** Raise the classes in `core/errors.py`; the handlers turn them
into `{"error": {"code", "message", "request_id"}}`. Messages say what to do next and never
echo source code or credentials.

**Comments explain why.** The code says what it does. Comments are for the constraint, the
incident, or the trade-off that made it this way.

**Style.** ruff (lint and format) and mypy in strict mode for Python; ESLint, Prettier and
strict TypeScript for the web app.

## Writing style

Commits, pull request text, documentation, code comments and user interface copy use commas,
colons, parentheses, the word "to" or a plain hyphen where other writing would use a long
dash. The commit hooks and `make sanitize` reject typographic dashes.

Commit messages and pull request descriptions describe the change. Do not add authorship
trailers, tool footers or session links; the commit author is the person who wrote the change.

## Commit messages

Imperative mood with a scope: `agent: refuse an empty search block on an existing file`,
`web: show the failing test first`. Explain the *why* in the body when it is not
obvious. Several small commits that each build and pass tests are easier to review than one
large one.

## Architecture decisions

A change that alters a documented decision (storage, indexing, the sandbox, how patches are
reviewed and applied, deployment topology) needs a new ADR in
[docs/architecture/adr/](docs/architecture/adr/), using the existing ones as a template.
