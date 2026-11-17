# Testing

| Suite              | Command                                     | What it covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API unit           | `make test` (pytest, `apps/api/tests/unit`) | Pure code: language detection, search terms, the index builder on the sample repositories, safe archive extraction, highlighting, embeddings, citations, the local answerer, model adapters (against a fake server), diffs, edit blocks, Python edits, mutations, the helper catalogue (each helper passes its own tests), planner skills end to end offline, the subprocess sandbox (limits, scrubbed environment, no network, JUnit), the Docker sandbox against a real engine (skipped without one), settings, passwords, sessions, API keys, rate limits, the error envelope, git, storage, queues and review exports |
| Web unit           | `make test` (Vitest, `apps/web`)            | URL state, API client, line anchors and hash parsing, SSE parsing, the Markdown subset and citation chips, diff comment grouping, file tree, roles and status labels, snippets that must run as written                                                                                                                                                                                                                                                                                                                                                                                                                   |
| API integration    | `make test-integration`                     | The real application over ASGI on real Postgres (pgvector), Valkey and the Floci emulator: upload and indexing, browsing, symbol, text and semantic search, cited answers and streaming, conversations, tasks (fix, rename, add, retry, cancel), review, apply to a branch and `git am` of the export, sandboxed runs with limits and isolation, the SQS worker, lost-message recovery and the backlog-aware reaper, tenant isolation of every route as an outsider, the role matrix, API keys, sessions, CSRF, rate limits, the OpenAPI document and the demo seed                                                       |
| Browser end-to-end | `make e2e` (Playwright, Chromium)           | Sign-in and role boundaries, browsing with line anchors, search, cited answers, the whole connect, test, review, approve and apply journey in a scratch workspace, API keys, people, the audit trail                                                                                                                                                                                                                                                                                                                                                                                                                      |
| QA crawl           | `make qa`                                   | Every page at 1440 and 390 px wide and in the dark theme: fails on console errors, uncaught exceptions, failed requests, sideways scrolling, broken links and serious or critical axe violations; saves a full-page capture of each page to `e2e/.qa/`                                                                                                                                                                                                                                                                                                                                                                    |
| Screenshots        | `make screenshots`                          | The README screenshots (1440x900 at 2x) and the tour GIF from the seeded stack                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

## Running them

```bash
make test                 # unit tests, no services needed (the Docker test skips itself without Docker)
make test-integration     # starts Postgres, Valkey and Floci if they are not up (scripts/test-deps.sh)
make up demo              # then the browser suites need the running stack
make e2e qa screenshots
```

The integration suite works in its own database (`codeagent_test`, recreated on every run),
Valkey database 15 and a bucket, key and queues it creates on the emulator, so the development
data is never touched. Point it elsewhere with `TEST_DATABASE_ADMIN_URL`, `TEST_REDIS_URL`,
`TEST_AWS_ENDPOINT_URL` and `TEST_DATABASE_NAME`.

The browser suites sign in as the demo people with `DEMO_PASSWORD` (read from
`deploy/compose/.env`). Each role's session is saved in `e2e/.auth` and reused, because sign-in
is rate limited. Specs that change data create a workspace of their own, so the demo workspace
the screenshots show stays as seeded. Failures keep a trace under `e2e/test-results`
(`pnpm exec playwright show-trace <zip>`).

## Style and static checks

```bash
make lint typecheck       # ruff, ESLint, Prettier; mypy (strict) and tsc
make sanitize             # credentials, account ids, typographic dashes
make tf-fmt tf-validate tf-lint tf-security
make gitleaks             # secrets in the full history
```

## Writing a test

- A new route is added to the outsider sweep in `tests/integration/test_access.py`, and the role
  matrix there if it changes data.
- A new planner skill gets unit tests like `tests/unit/test_agent_skills.py`: run the skill on a
  sample repository and run the sample's own tests on the result.
- Use `example.com` addresses in tests (the validator rejects the `.test` TLD).
