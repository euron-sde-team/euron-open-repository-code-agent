# Walkthrough

A guided tour of the demo workspace (`make up && make demo`). Sign in at
http://localhost:3190 as `priya.raman@example.com` (owner). The other people are
`marcus.lee@example.com` (maintainer), `sofia.alvarez@example.com` (developer) and
`tom.becker@example.com` (viewer), all with the password `make demo` prints.

## 1. Overview

Totals for the last 14 days, test runs per day (passed and failed), questions and searches,
tasks by outcome and recent work. "Awaiting review" and "Test pass rate" link to their lists.

## 2. Repositories and the code browser

Three repositories, each with a language bar and index status. Open **ledgerkit**: README,
index snapshots, test settings, recent tasks and runs. **Browse code** opens the file tree.
In `ledgerkit/pricing.py` click line numbers (shift-click extends a range; the URL carries
`#L18-L24`) and use the outline to open a symbol: its code, who calls it, what it calls and
which tests reference it.

## 3. Search

Symbols (`discount`), Text (`Decimal`, with a regular expression and a path glob) and By
meaning ("limit requests per client", which finds the Go limiter). Every result opens the
file at the matching lines.

## 4. Ask

"What does apply_discount do and which tests cover it?" The answer streams in, each claim has a
`[n]` chip, and **Sources** lists the cited files with their lines (expand one for the code).
Follow-ups ("And where is it called from?") keep the conversation as context. A question the
code cannot answer says so.

## 5. Tasks and review

- **#1 Fix the failing pricing test** (awaiting review): the agent found `test_discount_applies_at_threshold` failing, searched small code mutations in the sandbox and proposed changing `>` to `>=`. The review panel shows the suite before (31 of 32 passing) and after (32 of 32), the diff, a maintainer's line comment, and the trace.
- **#2 Rename** (applied): approved by the owner, applied to the branch `codeagent/2-...`; the export is a `git am`-ready `.patch`.
- **#3 Add clamp** (rejected, with a reason) and **#4 Add safe_divide** (awaiting review; its requester cannot approve it because the workspace requires an independent review).
- **#5** (failed): the offline planner cannot do open-ended changes and says what it can do.

Try: open #4 as Priya, comment on a line, approve it, apply it to a branch, download the patch.

## 6. Test runs

Each run shows its trigger (manual, agent baseline, agent verification), per-test results
(the failing test expanded with its assertion), the limits it ran under (no network, memory,
time) and the log.

## 7. Settings

People and roles, API keys (create one, copy the ready-to-run `curl`, revoke it), the engine
and sandbox in use, the audit trail, and your account.

## 8. From a script

```bash
KEY=cak_...      # the key `make demo` printed, or one you created
curl -s "http://localhost:8190/api/v1/workspaces/northwind-engineering/search/symbols?q=Invoice" \
  -H "Authorization: Bearer $KEY"
```
