# Threat Model

A STRIDE analysis of Euron CodeAgent as built. The controls referenced here are described in
[security.md](security.md).

## Assets

| Asset | Why it matters |
| --- | --- |
| Source code in the index, mirrors and archives | Often a company's most sensitive intellectual property |
| Accounts, sessions and API keys | They gate access to the code and to approvals |
| The integrity of repositories and patches | A bad change that is approved and merged is a supply-chain incident |
| The worker host and its credentials | Where repository code actually runs |
| Availability of search, answers and review | Teams depend on them during work |

## Actors

| Actor | Trust |
| --- | --- |
| Workspace member (viewer to owner) | Authenticated; limited by role |
| API key holder | Authenticated for one workspace; never a person |
| Author of an indexed repository | **Untrusted**: their code and tests run in the sandbox, their text reaches prompts |
| Outsider | Unauthenticated; can reach the sign-in page and the API |
| Model provider (optional) | Semi-trusted: sees the prompts it is given; its output is only ever a proposal |
| Operator | Trusted with the deployment |

## Trust boundaries

1. Browser to API (cookie or bearer token, origin check, rate limits).
2. API to worker through the queue (ids only; the worker re-reads rows).
3. Worker to sandbox (the only place repository code runs).
4. Worker to git hosts and the model provider (outbound, constrained).
5. Services to AWS (least-privilege task roles, KMS).

## Analysis

### Spoofing

| Threat | Mitigation |
| --- | --- |
| Credential stuffing or guessing | Argon2id, account lock after eight failures, per-address rate limit, uniform error and timing |
| Stolen session cookie | `httpOnly`, `Secure`, `SameSite=Lax`, expiry, `session_version` revocation, denylist on sign-out |
| Cross-site request forgery | Origin or Referer check on every unsafe cookie request; API keys use a header, not cookies |
| Stolen or leaked API key | Keyed hash storage, scoped to one workspace and role, expiry, revocation, last-used display; it can never approve |
| Forged queue messages | The queue is private and encrypted; messages carry ids, and the worker verifies state in the database before acting |

### Tampering

| Threat | Mitigation |
| --- | --- |
| A malicious or compromised model changes code | It can only propose a diff; approval is required and re-checked at apply time; the diff, rationale and test results are in front of the reviewer |
| A patch that differs from what was reviewed | A patch revision is immutable; a retry creates a new revision and supersedes the old; apply uses the stored diff with `git apply --check` |
| The requester approves their own change | `require_independent_review` blocks the requester |
| A crafted archive overwrites files outside its folder | Path validation, no links or devices, size, count and ratio caps (zip slip, tar bombs) |
| Crafted git configuration or hooks run commands | A locked-down git environment: no system or global config, hooks disabled, protocol allow-list |
| SQL injection through search | Static statements with bound parameters; patterns validated; statement timeout |
| Test code alters other runs or the host | Each run has its own copy of the tree in a throwaway container or directory |

### Repudiation

| Threat | Mitigation |
| --- | --- |
| Someone denies approving or applying a patch | The decision stores who and when; the audit trail records approve, reject, apply and member and key changes; commits carry `Approved-by` trailers |
| A key's actions cannot be attributed | Audit rows name the key; keys are individually revocable |

### Information disclosure

| Threat | Mitigation |
| --- | --- |
| One workspace reads another's code | Every query takes the workspace id; outsiders get 404; an integration test calls every route as an outsider; caches are keyed per tenant |
| A conversation is read by a colleague | Conversations are private to their owner (queries include the user id) |
| Tests exfiltrate secrets or the repository over the network | No network in the Docker backend; scrubbed environment; the AWS worker task has no route out except AWS endpoints |
| Tests read the worker's credentials | The environment is scrubbed; the container sees only its own tree; the subprocess backend runs as an unprivileged user |
| Secrets in logs | Redaction of sensitive field names; logs never include source code or answers |
| A model provider sees code | Off by default (local engines); when enabled, only retrieved snippets go to the configured provider, and the provider is shown on every answer |
| Prompt injection in repository text | The prompt marks code as data; citations are validated; a model cannot execute anything, only propose a diff for review |
| Object storage exposure | Private bucket, public access blocked, SSE-KMS, TLS-only |

### Denial of service

| Threat | Mitigation |
| --- | --- |
| Decompression bomb or giant archive | Size, count and ratio limits; upload size limit before parsing |
| Catastrophic regular expression | Nested quantifiers refused; statement timeout |
| Endless or fork-bomb tests | Time limit, process limit, memory limit, log cap, kill and remove |
| A flood of jobs | Rate limits on tasks, runs and uploads; bounded worker concurrency; the reaper skips resending into a backlog |
| A poison message | Three receives, then the dead-letter queue with an alarm |
| Slow clients and large bodies | Body size limit, request timeouts at the load balancer, WAF rate limit |

### Elevation of privilege

| Threat | Mitigation |
| --- | --- |
| A viewer or developer approves, applies or manages keys | Role checks in routes and services; tests enumerate the role matrix |
| An API key acts as a person | Keys carry only `viewer` or `developer`, cannot create conversations, comment, decide or manage keys |
| Container escape from the sandbox | No capabilities, no-new-privileges, non-root user, no network, no host mounts, cgroup limits; the Docker daemon is the residual risk (see below) |
| Writing to the worker's disk through a patch path | Edit paths reject absolute paths and `..`; the apply happens in a scratch checkout |
| A member promotes themselves | Only owners change roles; the last owner cannot be removed or demoted |

## Residual risks and accepted trade-offs

1. **The Docker socket.** The local worker mounts it to start sandbox containers, which is
   equivalent to root on that host. Acceptable on a developer machine; do not run that
   configuration on a shared host. A rootless engine or a remote engine endpoint removes it.
2. **The subprocess backend** is not a boundary against deliberately malicious native code.
   The AWS network posture limits what such code could reach; a per-run Fargate task is the
   planned backend ([ADR 0004](adr/0004-sandbox-backends.md)).
3. **DNS rebinding** between the git host check and `git clone` is possible in a narrow window;
   redirects are disabled and the AWS task has no route to private ranges.
4. **Answers can still be wrong or stale.** The offline answerer only states what the index
   contains and cites it, but a stale index answers about old code; the repository page shows
   the commit and the time of the current index, and a sync replaces it.
5. **Members can read all code in their workspace.** Per-repository permissions are on the
   roadmap; use separate workspaces for code that needs a tighter circle today.
