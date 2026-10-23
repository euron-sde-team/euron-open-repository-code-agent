"""Prometheus metrics, exposed at GET /metrics (the worker serves its own on WORKER_METRICS_PORT).

One process per container (scale out with containers, not uvicorn workers), so the default
registry is accurate without multiprocess mode.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "codeagent_http_requests_total",
    "HTTP requests by route template.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "codeagent_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
JOBS = Counter("codeagent_jobs_total", "Jobs handled by the worker.", ["type", "outcome"])
JOB_DURATION = Histogram(
    "codeagent_job_duration_seconds",
    "Job duration by type.",
    ["type"],
    buckets=(0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 900),
)
INDEXED_FILES = Counter(
    "codeagent_indexed_files_total", "Files indexed, by language.", ["language"]
)
INDEXED_SYMBOLS = Counter(
    "codeagent_indexed_symbols_total", "Symbols extracted, by kind.", ["kind"]
)
SANDBOX_RUNS = Counter(
    "codeagent_sandbox_runs_total",
    "Sandboxed command runs by backend and outcome.",
    ["backend", "outcome"],
)
SANDBOX_DURATION = Histogram(
    "codeagent_sandbox_run_duration_seconds",
    "Sandboxed command duration by backend.",
    ["backend"],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)
AGENT_RUNS = Counter(
    "codeagent_agent_runs_total", "Agent runs by planner skill and outcome.", ["skill", "outcome"]
)
SEARCHES = Counter("codeagent_searches_total", "Searches by mode.", ["mode"])
SEARCH_DURATION = Histogram(
    "codeagent_search_duration_seconds",
    "Search latency by mode.",
    ["mode"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
ANSWERS = Counter("codeagent_answers_total", "Answers by answerer.", ["answerer"])
MODEL_TOKENS = Counter(
    "codeagent_model_tokens_total", "Tokens sent to and received from models.", ["kind"]
)
EMBEDDING_CACHE = Counter(
    "codeagent_embedding_cache_total", "Embedding cache lookups by result.", ["result"]
)
