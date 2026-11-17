## What and why

<!-- One paragraph: the problem, and how this change solves it. Link the issue. -->

## How it was verified

- [ ] `make lint typecheck test`
- [ ] `make test-integration` (if API, database, queue, worker, search, the sandbox or review code changed)
- [ ] `make e2e` (if a user flow, the web app or the infrastructure changed)
- [ ] `make tf-validate tf-lint tf-security` (if Terraform changed)

## Checklist

- [ ] Docs updated (`docs/`, the configuration reference) for any behavior or config change
- [ ] `make openapi` re-run if a route changed
- [ ] New migration instead of editing an applied one
- [ ] Data stays in its workspace: every repository query takes the workspace id and an isolation test covers the new path
- [ ] Anything that runs repository code goes through the sandbox, never the API process
- [ ] A changed planner skill, ranking weight or answer rule has unit tests with worked examples
- [ ] A patch is still only applied after approval, and the decision is audited
- [ ] No secrets, account ids, real emails or hostnames (`make sanitize` is clean)
- [ ] Security-relevant change? Described the threat and mitigation above
