# Operations

## Processes

| Process | Command                                       | Scale                                                                                                                                            |
| ------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| API     | `uvicorn codeagent.main:create_app --factory` | Stateless; any number of replicas. Migrations run on boot under an advisory lock                                                                 |
| Worker  | `python -m codeagent.worker`                  | One or more. Jobs run with bounded concurrency; the reaper is elected through Valkey, so extra workers add throughput, not duplicate maintenance |
| Web     | `node apps/web/server.js`                     | Stateless                                                                                                                                        |
| CLI     | `codeagent <command>`                         | One-off                                                                                                                                          |

The CLI works without a terminal (it runs as an ECS one-off task):

```bash
codeagent migrate
codeagent user create --email you@example.com --name "You" --admin    # prints a temporary password when none is given
codeagent reindex <workspace-slug> <repository>                        # queue a fresh index
codeagent reap                                                         # resend stuck work once
codeagent openapi --out docs/api/openapi.json
codeagent demo seed                                                    # development only
```

Locally: `make demo`, `make reap`, and `docker compose ... exec api codeagent ...`.

## Health and metrics

- `/livez` is always 200 while the process runs. `/readyz` checks the database, Valkey and the queue and returns 503 with the failing check named.
- `/metrics` (API) and the worker's `WORKER_METRICS_PORT` serve Prometheus text: `codeagent_http_requests_total` and `_latency` by route template, `codeagent_jobs_total` and `_duration` by type and outcome, `codeagent_sandbox_runs_total` and `_duration` by backend, `codeagent_agent_runs_total`, `codeagent_answers_total`, `codeagent_searches_total`, model token counters, indexed files and symbols, and embedding cache hits and misses. Keep `/metrics` off the public load balancer (the AWS deployment does).
- Logs are JSON lines with the request id (`X-Request-Id` is echoed on every response and put in every error envelope). Sensitive field names are redacted.

## Jobs and recovery

Messages carry `{type, workspace_id, target_id}` only; the worker re-reads the row, so
duplicates are harmless. A message is deleted when the job has recorded its outcome and left on
the queue when the job asks to be retried; after three receives SQS moves it to the
dead-letter queue (alarm on it). The reaper resends:

- snapshots in `queued` or `indexing` past `STALE_JOB_MINUTES`,
- tasks in `queued` or `running`, and `applying` patches,
- manual and patch test runs in `queued` or `running`,

and fails work that has used three attempts. It skips a pass while the queue holds more than
`REAPER_MAX_BACKLOG` messages. Agent test runs live inside their task and are redone with it.

On shutdown (SIGTERM) the worker stops receiving, lets running jobs finish for up to two
minutes, then exits; whatever did not finish is picked up again by the reaper.

## Capacity

- **Database.** The index is the bulk: file content plus chunks and their 384-dimension vectors. Budget roughly 3 to 5 times the source size per kept snapshot (`SNAPSHOT_RETENTION`, default 3). Watch connections (`DATABASE_POOL_SIZE` per process) and the HNSW index size.
- **Valkey.** Small: caches, counters and locks. It must not evict (the AWS parameter group sets `noeviction`) because the session denylist lives there.
- **Worker.** CPU and memory for indexing and for each test run (`SANDBOX_MEMORY_MB` per run times concurrency). The AWS default is 2 vCPU and 4 GB with concurrency 2.
- **S3.** Archives and mirrors, versioned; old versions expire after 30 days.

## Backups and upgrades

- Back up PostgreSQL (RDS automated backups are on). The index can be rebuilt from the repositories (`codeagent reindex`), so the irreplaceable data is accounts, conversations, tasks, patches, reviews and the audit trail.
- Upgrade by deploying the new images; the API migrates on boot. Never edit an applied migration.
- Rotating `API_KEY_PEPPER` invalidates every API key; rotating `SESSION_SECRET` signs everyone out.

## Moving to a model

Set `LLM_PROVIDER` and `LLM_MODEL` (and a key through Secrets Manager on AWS). The provider shows
on each answer and patch. Switching providers never serves stale output: answers record which
engine produced them and embedding cache keys include the provider and width. Changing the
embedding model to a different width means re-indexing every repository after the migration.
