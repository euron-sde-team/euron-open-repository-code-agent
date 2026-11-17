# ADR 0009: Web sessions are signed cookies protected by origin checks; scripts use API keys

## Status

Accepted.

## Context

The web app and the API are on different origins locally (3190 and 8190) and one host in production. People need a session that JavaScript cannot read; scripts need a credential that is not a person.

## Decision

Sign-in sets an `httpOnly`, `SameSite=Lax` cookie holding an HS256 JWT with a `jti` and the user's `session_version`. A cookie request that changes state must carry an `Origin` (or `Referer`) in the allow-list. Bearer tokens are accepted for scripts and tests; API keys use `Authorization: Bearer cak_...`, never cookies, so they are not subject to forgery. Sign-out denylists the `jti`; a password change bumps `session_version`.

## Consequences

- Revocation depends on Valkey for single sign-outs (it fails closed); a version bump needs only the database.
- `SameSite=Lax` plus the origin check is the CSRF defence; there is no per-form token.

## Alternatives considered

Server-side session rows (a lookup per request for little gain); localStorage tokens (readable by any script on the page)..
