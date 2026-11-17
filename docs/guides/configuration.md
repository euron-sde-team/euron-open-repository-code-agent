# Configuration reference

Every setting is an environment variable read once at start-up by
`apps/api/src/codeagent/core/config.py` (pydantic-settings), validated and frozen. In the
compose stack, `deploy/compose/compose.yaml` and its overlays set them; a few are exposed as
`CODEAGENT_*` variables in `deploy/compose/.env`. With `APP_ENV=production` the process
refuses to start when a setting is unsafe and lists every problem at once.

## Core

| Variable                   | Default                                          | Meaning                                                                     |
| -------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------- |
| `APP_ENV`                  | `development`                                    | `development`, `test` or `production`. Production enforces the checks below |
| `PRODUCT_NAME`             | `Euron CodeAgent`                                | Name shown in the UI and the API docs                                       |
| `LOG_LEVEL` / `LOG_FORMAT` | `info` / `json`                                  | `debug`, `info`, `warning`, `error`; `json` or `console`                    |
| `WEB_URL`, `API_URL`       | `http://localhost:3190`, `http://localhost:8190` | Public URLs; `WEB_URL` joins the origin allow-list                          |
| `CORS_ORIGINS`             | the two local web origins                        | Comma-separated; `*` is refused in production                               |
| `MIGRATE_ON_BOOT`          | `false`                                          | Apply Alembic migrations on start (advisory-locked, safe with replicas)     |

## Data stores

| Variable                                      | Default                | Meaning                                                                                           |
| --------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                                | local Postgres on 5459 | `postgresql+asyncpg://...`; add `?ssl=require` for RDS                                            |
| `DATABASE_SECRET_ARN`                         | none                   | RDS-managed secret: the password is read for each new connection, so rotation needs no redeploy   |
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | `10`, `10`             | Connection pool                                                                                   |
| `REDIS_URL`                                   | local Valkey on 6419   | Caches, rate limits, locks, session denylist                                                      |
| `STORAGE_BACKEND`                             | `local`                | `local` (a directory) or `s3`. Production needs `s3`                                              |
| `STORAGE_DIR`                                 | `data/files`           | Directory for `local`                                                                             |
| `S3_BUCKET`, `S3_KMS_KEY_ID`                  | none                   | Bucket and SSE-KMS key (id, ARN or alias)                                                         |
| `AWS_REGION`, `AWS_ENDPOINT_URL`              | `us-east-1`, none      | The endpoint is set only for the emulator; production refuses it                                  |
| `QUEUE_BACKEND`                               | `inline`               | `inline` (jobs run in the API process, for tests and a lone API) or `sqs`. Production needs `sqs` |
| `SQS_QUEUE_URL`                               | none                   | The jobs queue                                                                                    |

## Security

| Variable                                                            | Default                             | Meaning                                                                            |
| ------------------------------------------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------------- |
| `SESSION_SECRET`                                                    | dev value                           | HS256 key for sessions. 32+ random characters in production                        |
| `API_KEY_PEPPER`                                                    | dev value                           | Pepper for the keyed hash of API key secrets. Must differ from `SESSION_SECRET`    |
| `SESSION_TTL_HOURS`                                                 | `168`                               | Session lifetime                                                                   |
| `COOKIE_SECURE`, `COOKIE_DOMAIN`                                    | `false`, none                       | `Secure` and `Domain` of the session cookie. Production needs `COOKIE_SECURE=true` |
| `ALLOW_SIGNUP`                                                      | `false`                             | Let anyone register. The first account on a deployment is always allowed           |
| `RATE_LIMIT_LOGIN`, `_ASK`, `_TASKS`, `_RUNS`, `_UPLOAD`, `_SEARCH` | `10`, `30`, `20`, `30`, `20`, `120` | Requests per minute per caller (per address for sign-in)                           |

## Repositories and the index

| Variable                           | Default        | Meaning                                                                                     |
| ---------------------------------- | -------------- | ------------------------------------------------------------------------------------------- |
| `MAX_ARCHIVE_MB`                   | `100`          | Largest upload; larger bodies are refused before parsing                                    |
| `MAX_REPO_MB`, `MAX_FILES`         | `500`, `20000` | Limits on what one repository may extract to                                                |
| `MAX_FILE_KB`                      | `512`          | Larger files are tracked but not indexed                                                    |
| `GIT_CLONE_DEPTH`, `GIT_TIMEOUT_S` | `50`, `180`    | Shallow clone depth and the timeout of git commands                                         |
| `ALLOW_PRIVATE_GIT_HOSTS`          | `false`        | Allow git URLs that resolve to private addresses (local git servers). Production refuses it |
| `SNAPSHOT_RETENTION`               | `3`            | Snapshots kept per repository                                                               |
| `CHUNK_MAX_LINES`                  | `60`           | Chunk size for embedding                                                                    |
| `SEARCH_TIMEOUT_MS`                | `3000`         | Statement timeout of text search                                                            |

## Jobs and the worker

| Variable                 | Default | Meaning                                                                 |
| ------------------------ | ------- | ----------------------------------------------------------------------- |
| `WORKER_CONCURRENCY`     | `2`     | Jobs one worker runs at once                                            |
| `JOB_TIMEOUT_S`          | `900`   | Longest a job may run; the queue's visibility timeout is this plus 120  |
| `WORKER_POLL_WAIT_S`     | `10`    | SQS long-poll wait                                                      |
| `STALE_JOB_MINUTES`      | `20`    | Work stuck in queued or running this long is resent by the reaper       |
| `MAINTENANCE_INTERVAL_S` | `60`    | How often the reaper runs (one worker at a time)                        |
| `REAPER_MAX_BACKLOG`     | `50`    | The reaper leaves stuck work alone while the queue holds more than this |
| `WORKER_METRICS_PORT`    | unset   | Serve the worker's Prometheus metrics on this port                      |

## Embeddings, answers and the agent

| Variable                                                             | Default                  | Meaning                                                                                              |
| -------------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------- |
| `EMBEDDINGS_PROVIDER`                                                | `local`                  | `local` (the offline `code-hash` embedder), `openai` or `ollama`                                     |
| `EMBEDDINGS_MODEL`, `EMBEDDING_DIM`                                  | `code-hash-v1`, `384`    | Model name and width. The width is fixed in the database column                                      |
| `EMBEDDINGS_API_BASE`, `EMBEDDINGS_API_KEY`, `EMBEDDINGS_BATCH_SIZE` | OpenAI base, none, `64`  | For `openai`                                                                                         |
| `LLM_PROVIDER`                                                       | `none`                   | `none` (local answerer and planner, fully offline), `openai` (any OpenAI-compatible API) or `ollama` |
| `LLM_MODEL`                                                          | empty                    | Required when a provider is set                                                                      |
| `LLM_BASE_URL`, `LLM_API_KEY`                                        | OpenAI base, none        | For `openai`                                                                                         |
| `OLLAMA_URL`                                                         | `http://localhost:11434` | For `ollama`                                                                                         |
| `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_S`                 | `0.1`, `1500`, `120`     | Generation settings                                                                                  |
| `AGENT_MAX_ITERATIONS`                                               | `2`                      | Model planner attempts when the tests fail after its edit                                            |
| `AGENT_MAX_CANDIDATES`                                               | `40`                     | Mutations the offline test-repair skill may try                                                      |
| `AGENT_CONTEXT_TOKENS`                                               | `6000`                   | Budget for the files given to the model planner                                                      |
| `ANSWER_SOURCES`                                                     | `8`                      | Sources given to an answerer                                                                         |

Any `none` or `local` choice makes no network call. The provider and model are stored with every
answer and patch.

## Sandbox

| Variable                                                                 | Default                   | Meaning                                                            |
| ------------------------------------------------------------------------ | ------------------------- | ------------------------------------------------------------------ |
| `SANDBOX_BACKEND`                                                        | `auto`                    | `docker`, `subprocess`, or `auto` (Docker when its socket answers) |
| `SANDBOX_DOCKER_SOCKET`                                                  | `/var/run/docker.sock`    | Where the Docker Engine listens                                    |
| `SANDBOX_IMAGE`                                                          | `codeagent-sandbox:local` | The image test runs start in (`make sandbox-image`)                |
| `SANDBOX_PYTHON`                                                         | `python3`                 | The interpreter the subprocess backend uses                        |
| `SANDBOX_TIMEOUT_S`, `SANDBOX_MEMORY_MB`, `SANDBOX_CPUS`, `SANDBOX_PIDS` | `300`, `1024`, `1`, `256` | Per-run ceilings; a repository's own settings can only lower them  |
| `SANDBOX_LOG_KB`                                                         | `512`                     | Cap on a run's log                                                 |

## Other

| Variable                                         | Default         | Meaning                                                                           |
| ------------------------------------------------ | --------------- | --------------------------------------------------------------------------------- |
| `EMBEDDING_CACHE_TTL_S`, `HIGHLIGHT_CACHE_TTL_S` | 30 days, 7 days | Cache lifetimes                                                                   |
| `DEMO_PASSWORD`                                  | none            | Password for the demo accounts (`codeagent demo seed`); refused in production     |
| `FORWARDED_ALLOW_IPS`                            | `127.0.0.1`     | Uvicorn's trusted proxies. Set to the VPC range behind a load balancer, never `*` |

## Compose variables (`deploy/compose/.env`)

| Variable                                                                               | Meaning                                          |
| -------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `CODEAGENT_SESSION_SECRET`, `CODEAGENT_API_KEY_PEPPER`, `CODEAGENT_DEMO_PASSWORD`      | Generated by `make env`                          |
| `CODEAGENT_LLM_PROVIDER`, `_LLM_MODEL`, `_LLM_BASE_URL`, `_LLM_API_KEY`, `_OLLAMA_URL` | Use a model instead of the offline engines       |
| `CODEAGENT_SANDBOX_BACKEND`                                                            | `auto`, `docker` or `subprocess`                 |
| `CODEAGENT_DOCKER_GID`                                                                 | Group of the Docker socket; `make up` detects it |
| `CODEAGENT_ALLOW_PRIVATE_GIT_HOSTS`                                                    | Connect git servers on this machine              |
| `CODEAGENT_WEB_PORT`, `_API_PORT`, `_PG_PORT`, `_REDIS_PORT`, `_FLOCI_PORT`            | Host ports (3190, 8190, 5459, 6419, 4619)        |

The web app reads `API_URL` and `PRODUCT_NAME` at run time from `/env.js`, so one image serves
every environment.
