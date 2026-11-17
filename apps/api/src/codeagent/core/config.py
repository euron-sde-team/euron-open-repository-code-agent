"""Runtime configuration, validated once at boot.

Every setting comes from the environment. `get_settings()` is cached, so the whole process
shares one frozen `Settings`. In production, `production_problems()` refuses development
defaults and reports every problem at once instead of one per restart.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Shipped so `uvicorn` starts with zero configuration on a laptop. Production refuses it.
DEV_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105

AppEnv = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: AppEnv = "development"
    product_name: str = "Euron CodeAgent"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "console"] = "json"

    # HTTP
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3190", "http://127.0.0.1:3190"]
    )
    web_url: str = "http://localhost:3190"
    api_url: str = "http://localhost:8190"

    # Postgres (pgvector, pg_trgm)
    database_url: str = "postgresql+asyncpg://codeagent:codeagent@localhost:5459/codeagent"
    # On AWS the URL carries no password; it is read from this RDS-managed secret for each
    # new connection, so a rotation needs no redeploy.
    database_secret_arn: str | None = None
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_echo: bool = False
    migrate_on_boot: bool = False

    # Valkey or Redis: caches, rate limits, locks, session revocation
    redis_url: str = "redis://localhost:6419/0"

    # Sessions and API keys
    session_secret: SecretStr = SecretStr(DEV_SECRET)
    session_ttl_hours: int = Field(default=168, ge=1, le=2160)
    api_key_pepper: SecretStr = SecretStr(DEV_SECRET)
    cookie_secure: bool = False
    cookie_domain: str | None = None
    allow_signup: bool = False

    # Archives, repository mirrors and test logs
    storage_backend: Literal["s3", "local"] = "local"
    storage_dir: Path = Path("data/files")
    s3_bucket: str | None = None
    s3_kms_key_id: str | None = None
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None

    # Jobs
    queue_backend: Literal["sqs", "inline"] = "inline"
    sqs_queue_url: str | None = None
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    job_timeout_s: int = Field(default=900, ge=30)
    stale_job_minutes: int = Field(default=20, ge=1)
    worker_poll_wait_s: int = Field(default=10, ge=0, le=20)
    maintenance_interval_s: int = Field(default=60, ge=10)
    # The reaper leaves stuck work alone while the queue holds more than this many messages:
    # resending into a backlog only makes it longer.
    reaper_max_backlog: int = Field(default=50, ge=1)

    # Repositories and the index
    max_archive_mb: int = Field(default=100, ge=1, le=2048)
    max_repo_mb: int = Field(default=500, ge=1)
    max_files: int = Field(default=20_000, ge=10)
    max_file_kb: int = Field(default=512, ge=1, le=10_240)
    git_clone_depth: int = Field(default=50, ge=1, le=10_000)
    git_timeout_s: int = Field(default=180, ge=10)
    allow_private_git_hosts: bool = False
    snapshot_retention: int = Field(default=3, ge=1, le=50)
    chunk_max_lines: int = Field(default=60, ge=10, le=400)

    # Embeddings. "local" is the deterministic code-hash embedder: no network, no download.
    embeddings_provider: Literal["local", "openai", "ollama"] = "local"
    embeddings_model: str = "code-hash-v1"
    embedding_dim: int = Field(default=384, ge=32, le=4096)
    embeddings_batch_size: int = Field(default=64, ge=1, le=512)
    embeddings_api_base: str = "https://api.openai.com/v1"
    embeddings_api_key: SecretStr | None = None

    # Answers and the agent. "none" keeps CodeAgent fully offline with the local answerer
    # and the local planner.
    llm_provider: Literal["none", "ollama", "openai"] = "none"
    llm_model: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    ollama_url: str = "http://localhost:11434"
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_max_tokens: int = Field(default=1500, ge=16, le=16_384)
    llm_timeout_s: float = Field(default=120.0, gt=0)

    agent_max_iterations: int = Field(default=2, ge=1, le=5)
    agent_max_candidates: int = Field(default=40, ge=1, le=200)
    agent_context_tokens: int = Field(default=6000, ge=500, le=100_000)
    answer_sources: int = Field(default=8, ge=1, le=20)

    # Sandboxed test runs
    sandbox_backend: Literal["auto", "docker", "subprocess"] = "auto"
    sandbox_docker_socket: str = "/var/run/docker.sock"
    sandbox_image: str = "codeagent-sandbox:local"
    sandbox_python: str = "python3"
    sandbox_timeout_s: int = Field(default=300, ge=5, le=3600)
    sandbox_memory_mb: int = Field(default=1024, ge=64, le=16_384)
    sandbox_cpus: float = Field(default=1.0, gt=0, le=16)
    sandbox_pids: int = Field(default=256, ge=16, le=4096)
    sandbox_log_kb: int = Field(default=512, ge=16, le=10_240)

    # Search
    search_timeout_ms: int = Field(default=3000, ge=100, le=60_000)

    # Caching
    embedding_cache_ttl_s: int = Field(default=30 * 24 * 3600, ge=0)
    highlight_cache_ttl_s: int = Field(default=7 * 24 * 3600, ge=0)

    # Rate limits, requests per minute per caller
    rate_limit_ask: int = Field(default=30, ge=1)
    rate_limit_login: int = Field(default=10, ge=1)
    rate_limit_tasks: int = Field(default=20, ge=1)
    rate_limit_runs: int = Field(default=30, ge=1)
    rate_limit_upload: int = Field(default=20, ge=1)
    rate_limit_search: int = Field(default=120, ge=1)

    demo_password: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_archive_bytes(self) -> int:
        return self.max_archive_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        # An archive upload plus its multipart framing; every other body is far smaller.
        return self.max_archive_bytes + 1024 * 1024

    @property
    def worker_visibility_s(self) -> int:
        # A received job stays hidden while it runs; the worker also extends it.
        return self.job_timeout_s + 120

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_kb * 1024

    @property
    def model_label(self) -> str:
        """Provider and model as shown to users and stored with each answer and patch."""
        if self.llm_provider == "none":
            return "local"
        return f"{self.llm_provider}:{self.llm_model or 'default'}"

    def production_problems(self) -> list[str]:
        """Every reason this configuration is unsafe to serve real users."""
        problems: list[str] = []
        session = self.session_secret.get_secret_value()
        pepper = self.api_key_pepper.get_secret_value()
        for name, value in (("SESSION_SECRET", session), ("API_KEY_PEPPER", pepper)):
            if value == DEV_SECRET or len(value) < 32:
                problems.append(f"{name} must be a random value of at least 32 characters")
        if session == pepper:
            problems.append("SESSION_SECRET and API_KEY_PEPPER must differ")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true behind HTTPS")
        if not self.cors_origins or "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list the web app origins explicitly")
        if self.storage_backend != "s3" or not self.s3_bucket:
            problems.append("STORAGE_BACKEND=s3 with S3_BUCKET is required")
        if self.queue_backend != "sqs" or not self.sqs_queue_url:
            problems.append("QUEUE_BACKEND=sqs with SQS_QUEUE_URL is required")
        if self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL points at an emulator; unset it in production")
        if self.allow_private_git_hosts:
            problems.append("ALLOW_PRIVATE_GIT_HOSTS lets git URLs reach internal addresses")
        if self.llm_provider != "none" and not self.llm_model:
            problems.append("LLM_MODEL is required when LLM_PROVIDER is set")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
