# ADR 0004: Tests run in a Docker container where a daemon exists, and in a limited subprocess where it does not

## Status

Accepted.

## Context

Running a repository's tests is the point of CodeAgent and also its biggest risk: the code is untrusted. Locally there is a Docker daemon. On AWS Fargate there is not, and giving a task privileged access to a daemon would defeat the purpose.

## Decision

`Sandbox` is a protocol with two backends, chosen by `SANDBOX_BACKEND` (`auto` uses Docker when its socket answers).

- **Docker:** a throwaway container per run from `codeagent-sandbox`, no network, all capabilities dropped, `no-new-privileges`, non-root user, memory (no swap), CPU, process and file limits, a tmpfs for `/tmp`, the tree copied in as a tar stream (no bind mounts), a deadline, and removal afterwards. The Engine API is spoken directly over the socket.
- **Subprocess:** a new session with `RLIMIT_*` limits, a scrubbed environment, a private directory and a network guard (`sitecustomize`) that refuses non-loopback sockets and lookups in Python.

Both return the same result (exit code, timing, capped log, JUnit XML). JUnit is parsed with `defusedxml`. The worker, the only component with the socket, removes labelled leftovers at start-up.

## Consequences

- The subprocess backend is a guard for honest suites, not a boundary against malicious native code. The AWS task therefore has no route beyond AWS endpoints and git hosts, and the documentation says so.
- Mounting the Docker socket into the local worker is root-equivalent on that host; this is accepted for a developer machine and documented.
- A stronger AWS backend, one Fargate task per run with its own network rules, is planned behind the same protocol.

## Alternatives considered

A language-level sandbox (cannot contain arbitrary test commands); gVisor or Firecracker (excellent, but not available on Fargate and heavy for a laptop); running tests in the API process (unacceptable)..
