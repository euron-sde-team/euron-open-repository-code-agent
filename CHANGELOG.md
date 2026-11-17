# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-17

First release.

### Added

- **Code index.** Upload an archive or give an HTTPS git URL. Files are classified by
  language, symbols and references are extracted (Python with `ast`; JavaScript, TypeScript,
  TSX and Go with tree-sitter), references are resolved into a call, import and inheritance
  graph, and every file is split into symbol-aware chunks that are embedded offline.
  Snapshots are written in one transaction and swapped in atomically.
- **Search.** Symbol search (exact, prefix and trigram), text search (literal or regular
  expression, with a guard against catastrophic patterns) and semantic search (vectors fused
  with keyword ranking), every hit linked to exact lines.
- **Answers with citations.** A deterministic local answerer composes cited answers from the
  index; OpenAI-compatible servers and Ollama plug in behind the same interface. Citation
  markers that point at an unknown source are removed. Answers stream as server-sent events.
- **Agent.** Offline skills rename a symbol through the reference graph, add a catalogued
  helper with tests, and repair a failing test by searching verified mutations. A model
  planner handles open-ended changes with search-and-replace edits and a test feedback loop.
- **Sandboxed test runs.** One throwaway Docker container per run with no network, dropped
  capabilities and cgroup limits, or a resource-limited subprocess where there is no Docker
  daemon. Results come from JUnit XML.
- **Review.** Unified diffs with syntax highlighting and line comments, approve or reject
  with a note, an optional independent-review rule, apply to a branch of the repository
  mirror, and export as `.diff` or a `git am`-ready `.patch`.
- **Web app.** Overview, repositories, a code browser with line anchors and a symbol panel,
  search, ask, tasks with diff review, test runs with logs, and settings, in light and dark.
- **Platform.** Workspaces with four roles, workspace API keys, an audit trail, rate limits,
  structured logs, Prometheus metrics, liveness and readiness probes, graceful shutdown, and
  a reaper that resends work whose queue message was lost.
- **Deployment.** Docker Compose on the Floci AWS emulator provisioned by the same Terraform
  that builds AWS (S3, SQS, KMS, Secrets Manager), and Terraform for `aws-dev` and `aws-prod`
  on ECS Fargate, RDS, ElastiCache, an ALB with WAF and CloudWatch alarms.
