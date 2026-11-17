# Security

How CodeAgent protects the code it indexes, the people who use it and the machine it runs on.
The threats behind these controls are analysed in [threat-model.md](threat-model.md).

- [Principles](#principles)
- [Authentication](#authentication)
- [Authorization](#authorization)
- [Running untrusted code](#running-untrusted-code)
- [Importing code](#importing-code)
- [Changes to code](#changes-to-code)
- [Data protection](#data-protection)
- [Web and API hardening](#web-and-api-hardening)
- [Models and prompts](#models-and-prompts)
- [Secrets](#secrets)
- [Logging and audit](#logging-and-audit)
- [Operator checklist](#operator-checklist)

## Principles

1. **Repository code is hostile until proven otherwise.** It is read as text everywhere except
   one place, the sandbox, where it runs with no network and hard limits.
2. **Agents propose, people decide.** Nothing reaches a repository's mirror without a
   maintainer's approval, which the worker checks again under a row lock.
3. **A workspace is the tenant boundary.** Every query that reads workspace data takes the
   workspace id, and non-members get 404, not 403, so existence is not revealed.
4. **Fail closed in production.** The process refuses to start with development secrets,
   insecure cookies, open CORS, local storage or the inline queue, an emulator endpoint or
   private git hosts allowed (`Settings.production_problems()` lists every problem at once).

## Authentication

- **People** sign in with email and password. Passwords are hashed with Argon2id (64 MiB,
  3 iterations), verified off the event loop, and compared against a dummy hash when the
  email is unknown, so timing does not reveal which accounts exist. Eight failed attempts lock
  the account for fifteen minutes; sign-in is also rate limited per address.
- **Sessions** are HS256 JWTs (issuer, audience, `jti`, expiry) in an `httpOnly`, `SameSite=Lax`
  cookie, `Secure` in production. A token carries the user's `session_version`: changing the
  password bumps it and signs out every other browser. Signing out puts the `jti` on a Valkey
  denylist until it would have expired; if Valkey is down, sign-in and revocation fail closed.
- **Cookie sessions are origin-checked.** Unsafe methods must come from the web app's own
  origin (`Origin`, else `Referer`), which closes cross-site request forgery.
- **API keys** are `cak_<prefix>_<secret>`. Only an HMAC-SHA256 of the secret keyed with a
  server-side pepper is stored, so a database leak alone cannot be replayed. Keys are bound to
  one workspace, carry the `viewer` or `developer` role, can expire and can be revoked, and
  `last_used_at` is updated at most once a minute.
- **Sign-up** is closed by default; the first account on a deployment becomes its
  administrator, later people are added by a workspace owner (who gets a one-time temporary
  password for new accounts).

## Authorization

| Role       | May                                                                                    |
| ---------- | -------------------------------------------------------------------------------------- |
| viewer     | Read code, search, ask, read tasks, patches and test runs                              |
| developer  | Plus: describe tasks, retry and cancel them, comment on patches, run tests             |
| maintainer | Plus: connect, sync, change and delete repositories; approve, reject and apply patches |
| owner      | Plus: members, API keys, workspace settings, the audit trail                           |

API keys are never people: they cannot comment, approve or apply, create conversations or
manage keys. With `require_independent_review`, the person who asked for a task cannot decide
its patch. Roles are checked in routes (`access.require`) and again in services where a rule
needs the data (the independent-review rule, comment ownership).

## Running untrusted code

Tests are code from the repository, so they run only in the sandbox (`sandbox/`):

| Control          | Docker backend (default where a daemon exists)                                                                             | Subprocess backend (Fargate)                                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Network          | `NetworkDisabled`, `NetworkMode: none`                                                                                     | proxy variables pointing at a closed port, and a `sitecustomize` guard refusing non-loopback sockets and name lookups (Python only) |
| Filesystem       | the tree is copied in as a tar stream: no bind mounts, nothing of the host is visible; the container is removed afterwards | a fresh temporary directory, removed afterwards                                                                                     |
| Privileges       | non-root user, `CapDrop: ALL`, `no-new-privileges`                                                                         | the worker's unprivileged user, a new session and process group                                                                     |
| CPU, memory      | `NanoCpus`, `Memory` equal to `MemorySwap` (so no swap)                                                                    | `RLIMIT_CPU`, `RLIMIT_AS` (Linux)                                                                                                   |
| Processes, files | `PidsLimit`, `nofile` ulimit, a 256 MB tmpfs                                                                               | `RLIMIT_NPROC` (Linux), `RLIMIT_NOFILE`, `RLIMIT_FSIZE`, no core dumps                                                              |
| Time             | wait with a deadline, then kill the container                                                                              | wait with a deadline, then kill the process group                                                                                   |
| Environment      | only what the run sets                                                                                                     | scrubbed to `PATH`, `HOME`, locale and test variables: the worker's secrets never reach the tests                                   |
| Output           | the log is capped; JUnit XML is parsed with `defusedxml`                                                                   | same                                                                                                                                |

The Docker backend is a security boundary. The subprocess backend is a guard for honest test
suites, not a boundary: code that loads a native library or starts another runtime can get
around the Python network guard. That is why the AWS deployment gives the worker task a
security group with no route to anything but the AWS endpoints it needs, and why the
[ADR](adr/0004-sandbox-backends.md) records a per-run Fargate task as the planned stronger
backend. The worker mounts the Docker socket locally to create containers, which is
equivalent to root on that host: it is acceptable on a developer machine and the documentation
says so; do not run a stack that mounts it on a shared host.

## Importing code

- **Git URLs** must be HTTPS without credentials. Hosts that resolve to private, loopback,
  link-local or reserved addresses are refused unless `ALLOW_PRIVATE_GIT_HOSTS=true` (which
  production refuses). Every git command runs with `GIT_TERMINAL_PROMPT=0`, no global or
  system configuration, `core.hooksPath=/dev/null`, `protocol.allow=never` with only `https`
  (and `file` for the local mirror), no redirects to other hosts, and a timeout. The API never
  shells out to git; the worker does.
- **Archives** are extracted by `codeintel/archive.py`: absolute paths and `..` are refused,
  links and device files are skipped, and the entry count, the size of every file, the total
  size and the compression ratio are capped. A single wrapper folder is unwrapped safely.
- **Files** are decoded as UTF-8 with replacement, binary files (a NUL byte in the first 8 KB)
  and files over `MAX_FILE_KB` are tracked but not indexed, and vendored or generated
  directories are skipped.
- **Search** statements are static SQL with bound parameters. Regular expressions with nested
  quantifiers are refused up front, and every text search runs under a statement timeout.

## Changes to code

The agent writes to a scratch checkout, never to the mirror. Applying a patch needs: an
approved revision, a maintainer, and a second look by the worker under a row lock. The branch
name is validated, the patch is checked with `git apply --check`, and the commit is made with
the CodeAgent identity plus `Requested-by` and `Approved-by` trailers. CodeAgent never pushes
to a git host. Every decision and apply is in the audit trail.

## Data protection

- Postgres holds the index and history; Valkey holds caches, rate limits, locks and the session
  denylist; S3 holds archives, mirrors and logs.
- On AWS, S3 objects use SSE-KMS with the deployment key and a bucket key, the bucket blocks all
  public access, is versioned and denies non-TLS requests. RDS storage, ElastiCache,
  Secrets Manager, ECR, SQS and CloudWatch Logs use the same key. Postgres connections require
  TLS; the database password lives in an RDS-managed secret and is read for each new connection,
  so rotation needs no redeploy. Valkey requires TLS and an auth token.
- Every cache key includes what makes it unique (provider and width for embeddings, file id for
  highlighting, workspace id for the overview), so one tenant never hits another's entry.
- Deleting a repository or workspace deletes the rows and the S3 prefix.

## Web and API hardening

- One error envelope with a request id; unexpected errors reveal nothing but the id.
- Security headers on every response (`nosniff`, `no-referrer`, `DENY` framing, CORP same-site,
  HSTS in production); the web app adds a permissions policy.
- Bodies are limited before the multipart parser buffers them.
- Rate limits per caller for sign-in, questions, searches, task creation, test runs and uploads.
- Uvicorn trusts `X-Forwarded-For` only from the VPC range. `/metrics` is not routed by the
  load balancer. The WAF (production) applies the AWS managed common, known-bad-inputs and IP
  reputation sets plus a rate limit.
- The web app renders file content and model output as text nodes only, and never injects HTML.
  Answer text is parsed into a small set of React elements; links are built from validated
  fields, never from the text.

## Models and prompts

By default nothing leaves the deployment: the local answerer and planner make no network calls.
When a provider is configured, the system prompt requires citations and treats repository
content as data, not instructions; sources are fenced; the answer's citations are validated
against the sources it was given; planner edits are applied as exact search-and-replace blocks
and rejected when they do not match, never guessed. A model can only propose a diff, which
still goes through review. The provider and model are shown on every answer and patch.

## Secrets

`SESSION_SECRET` and `API_KEY_PEPPER` are generated per deployment (`make env` locally, Secrets
Manager on AWS), must be different, and are refused when they are development defaults. LLM
keys come from the environment or Secrets Manager, are `SecretStr`, and log fields with
`password`, `secret`, `token`, `authorization`, `api_key` or `cookie` in their name are
redacted. gitleaks runs in CI over the full history, and `make sanitize` blocks account ids,
resource ids and private keys.

## Logging and audit

Structured JSON logs carry the request id; request logging skips probes. The audit trail
(`/workspaces/{ws}/audit`, owners) records who did what; it never contains source code.
Prometheus metrics expose counts and latencies only.

## Operator checklist

- [ ] `APP_ENV=production` (the process then refuses unsafe settings)
- [ ] HTTPS at the edge; `COOKIE_SECURE=true`; `CORS_ORIGINS` lists the web origin only
- [ ] `SESSION_SECRET` and `API_KEY_PEPPER` random, 32+ characters, different from each other
- [ ] Create the administrator before sharing the URL (`make aws-cli ARGS="user create ..."`)
- [ ] `ALLOW_SIGNUP=false` unless you want anyone to be able to register
- [ ] The worker's task has no route to the internet beyond AWS endpoints and the git hosts you use
- [ ] `/metrics` and the worker's metrics port are not reachable from the internet
- [ ] Turn on `require_independent_review` for workspaces where changes need a second person
- [ ] Alarm on the dead-letter queue, readiness and the database
- [ ] Rotate keys (`API_KEY_PEPPER` invalidates every API key; `SESSION_SECRET` signs everyone out)
