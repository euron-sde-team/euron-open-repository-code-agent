# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.x (latest minor) | Yes |
| Older minors | No |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include:

- the affected component (`apps/api`, `apps/web`, `infra/docker`, `infra/terraform/...`) and
  the version or commit,
- a description of the issue and its impact,
- steps to reproduce, or a proof of concept,
- any suggested mitigation.

Do not include real credentials or other people's source code in a report. A reproduction that
uses the bundled sample repositories (`make demo`) or invented code is enough.

What to expect:

| Stage | Target |
| ----- | ------ |
| Acknowledgement | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation for critical and high issues | within 30 days |
| Coordinated public disclosure | after a fix is released, credited to you unless you prefer otherwise |

## Safe harbour

We will not pursue or support legal action against people who find and report issues in good
faith under this policy: testing only against your own deployment (or the local stack from
`make up`), accessing no more data than needed to show the problem, not degrading a service
for others, and giving us reasonable time to fix before disclosing.

## Scope

In scope: the code in this repository and the infrastructure it provisions with its default
settings. The most important classes of issue for this project are:

- **Escaping the sandbox**: a repository's code or tests reading the host, the worker's
  environment or credentials, reaching the network, exceeding the memory, CPU, process or
  time limits, or surviving its run. This includes archives and git repositories crafted to
  write outside their directory (path traversal, links, decompression bombs, hostile git
  configuration or hooks).
- **Crossing a workspace boundary**: reading, searching, changing or deleting another
  workspace's repositories, code, answers, tasks, patches or test runs, with a session or an
  API key; or reading another person's conversations in the same workspace.
- **Changing code without approval**: applying, or causing to be applied, a patch that a
  maintainer has not approved, or bypassing the independent-review rule.
- **Server-side request forgery through git URLs**: making a CodeAgent server fetch from an
  address it refuses by policy (private ranges, loopback, link-local, cloud metadata),
  including through redirects or DNS tricks.
- **API key or session forgery**, bypassing the cookie origin check, and privilege escalation
  between the `viewer`, `developer`, `maintainer` and `owner` roles, or by an API key (which
  can never approve a patch or manage keys).

Out of scope:

- **Content a workspace member can already read.** Members read every file of every
  repository in their workspace by design, and search results and answers quote the code.
- **What a repository's own code does inside the sandbox.** Tests are code: they may use all
  of their CPU time and memory up to the limits and write inside their own copy of the tree.
  Reports that cross a limit or leave the sandbox are in scope.
- **The subprocess backend is a guard, not a boundary.** Where there is no Docker daemon
  (Fargate), tests run in a resource-limited subprocess with a network guard for Python; the
  documented deployment gives that task no route to anything but AWS endpoints. Isolation
  claims apply to the Docker backend.
- **The demo seed.** `make demo` creates well-known demo accounts; it refuses to run with
  `APP_ENV=production`.
- Findings that need a compromised host, a compromised AWS account or leaked deployment
  secrets.
- Denial of service through resource exhaustion of a deployment you operate yourself, and
  missing rate limits on routes that are already authenticated.

## Hardening checklist for operators

See [docs/architecture/security.md](docs/architecture/security.md#operator-checklist).
