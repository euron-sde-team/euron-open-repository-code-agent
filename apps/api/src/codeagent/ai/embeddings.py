"""Embedding providers behind one interface, with a shared Valkey cache.

| Provider | Runs | Use |
| local    | in process: `code-hash`, deterministic feature hashing for code | default, offline |
| openai   | any OpenAI-compatible /embeddings endpoint, truncated to EMBEDDING_DIM | hosted |
| ollama   | a local Ollama server (/api/embed) | local GPU or CPU |

Every vector is L2-normalised, so cosine similarity is a dot product everywhere.

The local embedder needs no model and no network. It hashes the features a code reader
cares about into a fixed-width vector: the sub-tokens of identifiers (`calcTaxRate` ->
calc, tax, rate), adjacent word pairs, character trigrams of longer words (so `calc`
meets `calculate`), and concepts from a small programming lexicon (so `remove` meets
`delete`). It is not a neural model, and it does not pretend to be: it makes semantic
search useful offline and keeps tests, the demo and screenshots reproducible.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Sequence
from itertools import pairwise
from typing import Any, Protocol

import httpx
import numpy as np
from redis.asyncio import Redis

from codeagent.codeintel.terms import concepts, terms
from codeagent.core import metrics
from codeagent.core.config import Settings
from codeagent.core.errors import UpstreamError
from codeagent.core.logging import get_logger

log = get_logger("codeagent.embeddings")
Matrix = np.ndarray[Any, np.dtype[np.float32]]

PAIR_WEIGHT = 0.5
CONCEPT_WEIGHT = 0.7
TRIGRAM_WEIGHT = 0.12


def first_row(matrix: Matrix) -> Matrix:
    row: Matrix = matrix[0]
    return row


def normalize_rows(matrix: Matrix) -> Matrix:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized: Matrix = (matrix / norms).astype(np.float32)
    return normalized


class Embedder(Protocol):
    name: str
    dim: int

    async def embed_documents(self, texts: Sequence[str]) -> Matrix: ...

    async def embed_query(self, text: str) -> Matrix: ...


def code_features(text: str) -> dict[str, float]:
    """The weighted features the local embedder hashes (exposed for tests and tuning)."""
    words = terms(text)
    features: defaultdict[str, float] = defaultdict(float)
    for word in words:
        features[word] += 1.0
        concept = concepts(word)
        if concept:
            features[f"c:{concept}"] += CONCEPT_WEIGHT
    for a, b in pairwise(words):
        if a != b:
            features[f"{a} {b}"] += PAIR_WEIGHT
    for word in set(words):
        if len(word) >= 5:
            for i in range(len(word) - 2):
                features[f"g:{word[i : i + 3]}"] += TRIGRAM_WEIGHT
    return dict(features)


class CodeHashEmbedder:
    """Signed feature hashing of code-aware features. Deterministic across processes."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.name = f"code-hash-{dim}"

    def _vector(self, text: str) -> Matrix:
        vector = np.zeros(self.dim, dtype=np.float32)
        for feature, weight in code_features(text).items():
            digest = int.from_bytes(
                hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little"
            )
            sign = 1.0 if digest >> 63 else -1.0
            # Sublinear term frequency: a name repeated ten times is not ten times as relevant.
            value = 1 + math.log(weight) if weight >= 1 else weight
            vector[digest % self.dim] += sign * value
        return vector

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return normalize_rows(np.stack([self._vector(t) for t in texts]).astype(np.float32))

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))


class OpenAIEmbedder:
    def __init__(
        self, base_url: str, api_key: str | None, model: str, dim: int, timeout: float
    ) -> None:
        self.name = model
        self.dim = dim
        headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self.name, "input": list(texts), "dimensions": self.dim},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The embedding provider request failed.") from exc
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        matrix = np.asarray([item["embedding"] for item in data], dtype=np.float32)
        if matrix.shape[1] != self.dim:
            raise UpstreamError(
                f"{self.name} returned {matrix.shape[1]} dims; EMBEDDING_DIM is {self.dim}."
            )
        return normalize_rows(matrix)

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaEmbedder:
    def __init__(self, url: str, model: str, dim: int, timeout: float) -> None:
        self.name = model
        self.dim = dim
        self._client = httpx.AsyncClient(base_url=url.rstrip("/"), timeout=timeout)

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        try:
            response = await self._client.post(
                "/api/embed", json={"model": self.name, "input": list(texts)}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The Ollama embedding request failed.") from exc
        matrix = np.asarray(response.json()["embeddings"], dtype=np.float32)
        if matrix.shape[1] != self.dim:
            raise UpstreamError(
                f"{self.name} produces {matrix.shape[1]} dims; EMBEDDING_DIM is {self.dim}."
            )
        return normalize_rows(matrix)

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))

    async def aclose(self) -> None:
        await self._client.aclose()


class CachedEmbedder:
    """Read-through Valkey cache keyed by provider, width and the SHA-256 of the text.

    Re-indexing a repository after a small change costs one cache round trip for every
    chunk that did not change, instead of a model call.
    """

    def __init__(self, inner: Embedder, redis: Redis, ttl_s: int) -> None:
        self.inner = inner
        self.name = inner.name
        self.dim = inner.dim
        self._redis = redis
        self._ttl = ttl_s

    def _key(self, text: str, kind: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        return f"emb:{self.name}:{self.dim}:{kind}:{digest}"

    async def _cached(self, texts: Sequence[str], kind: str) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        keys = [self._key(t, kind) for t in texts]
        try:
            stored = await self._redis.mget(keys)
        except Exception:
            stored = [None] * len(texts)
        result = np.zeros((len(texts), self.dim), dtype=np.float32)
        missing = [i for i, raw in enumerate(stored) if raw is None]
        for i, raw in enumerate(stored):
            if raw is not None:
                buffer = raw.encode("latin-1") if isinstance(raw, str) else raw
                result[i] = np.frombuffer(buffer, dtype=np.float32)
        metrics.EMBEDDING_CACHE.labels("hit").inc(len(texts) - len(missing))
        metrics.EMBEDDING_CACHE.labels("miss").inc(len(missing))
        if missing:
            fresh = (
                await self.inner.embed_documents([texts[i] for i in missing])
                if kind == "doc"
                else np.stack([await self.inner.embed_query(texts[i]) for i in missing])
            )
            for row, i in enumerate(missing):
                result[i] = fresh[row]
            try:
                async with self._redis.pipeline(transaction=False) as pipe:
                    for row, i in enumerate(missing):
                        pipe.set(keys[i], fresh[row].tobytes(), ex=self._ttl or None)
                    await pipe.execute()
            except Exception:
                log.warning("embedding_cache_write_failed")
        return result

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        return await self._cached(texts, "doc")

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self._cached([text], "query"))


def build_embedder(settings: Settings) -> Embedder:
    match settings.embeddings_provider:
        case "openai":
            key = (
                settings.embeddings_api_key.get_secret_value()
                if settings.embeddings_api_key
                else None
            )
            return OpenAIEmbedder(
                settings.embeddings_api_base,
                key,
                settings.embeddings_model,
                settings.embedding_dim,
                60.0,
            )
        case "ollama":
            return OllamaEmbedder(
                settings.ollama_url, settings.embeddings_model, settings.embedding_dim, 60.0
            )
        case _:
            return CodeHashEmbedder(settings.embedding_dim)
