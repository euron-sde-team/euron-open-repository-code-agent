from __future__ import annotations

from codeagent.schemas.common import ApiModel


class EngineInfo(ApiModel):
    label: str
    provider: str
    model: str | None
    uses_model: bool


class SandboxInfo(ApiModel):
    backend: str
    image: str | None
    timeout_s: int
    memory_mb: int
    cpus: float
    network: str


class SystemInfo(ApiModel):
    product_name: str
    version: str
    answerer: EngineInfo
    planner: EngineInfo
    skills: list[str]
    helpers: list[str]
    embeddings: str
    embedding_dim: int
    sandbox: SandboxInfo
    max_archive_mb: int
    allow_signup: bool
    needs_setup: bool
