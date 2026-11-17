# API

The REST API is under `/api/v1`. The machine-readable reference is
[openapi.json](openapi.json), generated from the routes (`make openapi`); a running stack serves
an interactive version at http://localhost:8190/docs.

## Authentication

- **API keys** for scripts: `Authorization: Bearer cak_<prefix>_<secret>`. Create one in Settings,
  API keys (owners). A key belongs to one workspace and has the `viewer` or `developer` role.
- **Sessions** for the web app: `POST /api/v1/auth/login` sets an `httpOnly` cookie (and returns the token, which also works as a bearer token). Cookie requests that change state must come from the web app's origin.

## Conventions

- Workspace routes are `/api/v1/workspaces/{workspace}/...`; `{workspace}` is the slug or the id. A workspace you do not belong to answers 404.
- Lists take `limit` and `offset` and return `{items, total, limit, offset}` (a few small lists return arrays).
- Tasks and test runs are addressed by their number (`/tasks/12`) or id; patches by id.
- Every response has `X-Request-Id`. Errors are always `{"error": {"code", "message", "request_id", "details?"}}` with the right status: 401 not signed in, 403 role too low, 404 not found or not yours, 409 conflict (for example a patch that is not approved), 413 too large, 422 invalid, 429 rate limited (with `Retry-After`).
- Rate limit headers: `X-RateLimit-Limit`, `-Remaining`, `-Reset`.

## A tour with curl

```bash
API=http://localhost:8190/api/v1/workspaces/northwind-engineering
KEY=cak_...

# find a definition, then read its callers and tests
curl -s "$API/search/symbols?q=apply_discount" -H "Authorization: Bearer $KEY"
curl -s "$API/symbols/<id from the hit>" -H "Authorization: Bearer $KEY"

# search text (regex), and by meaning
curl -s "$API/search/text?q=def%20calc_%5Cw%2B&regex=true" -H "Authorization: Bearer $KEY"
curl -s "$API/search/semantic?q=limit%20requests%20per%20client" -H "Authorization: Bearer $KEY"

# ask, with citations (add /stream for server-sent events: sources, delta, done)
curl -s "$API/ask" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"question": "Where is the tax for an invoice calculated?"}'

# ask the agent for a change (developer key), then follow it
curl -s "$API/tasks" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"repository": "ledgerkit", "title": "Add clamp", "description": "add `clamp` to ledgerkit/pricing.py"}'
curl -s "$API/tasks/6" -H "Authorization: Bearer $KEY"
```

Reviewing is for people: approving, rejecting and applying a patch need a signed-in maintainer
or owner, and an API key can never do them.

## Route groups

Repositories (connect, upload, sync, files, blobs, symbols), search (symbols, text, semantic),
answers (conversations, messages, ask, streams), tasks, review (patches, comments, decisions,
apply, export), test runs, workspaces (members, API keys, audit, overview), auth, and system
(`/system/info`, `/livez`, `/readyz`). [LLD section 12](../architecture/LLD.md#12-api-surface)
lists every route.
