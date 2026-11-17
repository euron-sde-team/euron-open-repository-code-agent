# Troubleshooting

## The stack

| Symptom | Cause and fix |
| --- | --- |
| `make up` fails in `terraform` with `releases.hashicorp.com: unexpected EOF` | A network flake while downloading providers. Run `make up` again; the `codeagent-tf-plugins` volume caches them |
| `make up` is slow the first time | Three images build and Terraform applies to the emulator (3 to 5 minutes). Later runs reuse layers |
| `Cannot connect to the Docker daemon` | Start your engine (`colima start`, or Docker Desktop) |
| Port already allocated | Another process uses 3190, 8190, 5459, 6419 or 4619. Set `CODEAGENT_WEB_PORT`, `_API_PORT`, `_PG_PORT`, `_REDIS_PORT` or `_FLOCI_PORT` in `deploy/compose/.env` |
| `run \`make env\` first` | `deploy/compose/.env` is missing: `make env` creates it |
| The worker is unhealthy | `make logs SERVICE=worker`. It waits for the API (migrations) and the sandbox image |

## Test runs

| Symptom | Cause and fix |
| --- | --- |
| A run is `error`: "sandbox image is not available" | `make sandbox-image` (compose builds it too) |
| Runs use the `subprocess` backend although Docker is installed | The worker cannot read the Docker socket. `make up` detects its group; set `CODEAGENT_DOCKER_GID` in `deploy/compose/.env` if the socket lives somewhere unusual |
| "This repository has no test command" | Set one in the repository's settings |
| A run is `timed_out` | Raise the repository's time limit (capped by `SANDBOX_TIMEOUT_S`) |
| The tests need a package that is not installed | The sandbox image has Python and pytest only, and no network. Vendor the dependency or build your own image (`SANDBOX_IMAGE`) that includes it |
| Node or Go tests do not run | The shipped sandbox is Python-only. Use an image with your toolchain and set the repository's test command |

## Repositories and search

| Symptom | Cause and fix |
| --- | --- |
| Indexing fails with "outside its root" or "damaged" | The archive has unsafe paths or is corrupt; re-create it from a clean checkout |
| Git URL refused ("private address") | CodeAgent does not clone from private addresses unless `ALLOW_PRIVATE_GIT_HOSTS=true` (never in production) |
| A file is "Not indexed" | It is binary or larger than `MAX_FILE_KB` |
| Symbols are missing for a file | The file has a syntax error (a warning is shown on the repository) or its language has no extractor (Python, JavaScript, TypeScript, TSX and Go are supported); it is still searchable |
| Text search says "took too long" | Add a path glob or a more specific pattern |
| Nothing found by meaning | The offline embedder matches identifiers and common programming words; name what the code does in its own vocabulary, or configure an embedding model |

## Answers and tasks

| Symptom | Cause and fix |
| --- | --- |
| "I could not find this in the indexed code" | The index holds nothing that shares a word with the question. Name a function, class or file |
| A task fails with "unsupported" | The offline planner handles renames, failing tests and catalogued helpers. Configure a model for anything else |
| "The repository has no index yet" | Wait for indexing to finish |
| A task stays queued | The worker is down or backed up: `make ps`, `make logs SERVICE=worker`. After 20 minutes the reaper resends it |
| Apply failed | The patch no longer applies to the mirror. The git error is on the patch; retry the task for a fresh revision |

## Sign-in

| Symptom | Cause and fix |
| --- | --- |
| "Too many failed sign-ins" | Eight wrong passwords lock the account for 15 minutes |
| 429 on sign-in | Ten attempts a minute per address; wait a minute |
| Redirected to sign-in after a password change | Changing it signs out every other session |
| A cookie request is refused with `csrf` | The request did not come from the web app's origin; call the API with an API key instead |
