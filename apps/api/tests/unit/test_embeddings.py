from __future__ import annotations

import numpy as np
import pytest

from codeagent.ai.embeddings import CachedEmbedder, CodeHashEmbedder, code_features


@pytest.fixture
def embedder() -> CodeHashEmbedder:
    return CodeHashEmbedder(384)


async def test_vectors_are_deterministic_and_normalised(embedder: CodeHashEmbedder) -> None:
    first = await embedder.embed_documents(["def apply_discount(subtotal): return subtotal"])
    second = await embedder.embed_documents(["def apply_discount(subtotal): return subtotal"])
    assert first.shape == (1, 384)
    assert np.allclose(first, second)
    assert abs(float(np.linalg.norm(first[0])) - 1.0) < 1e-5


async def test_identifier_parts_make_related_code_similar(embedder: CodeHashEmbedder) -> None:
    query = await embedder.embed_query("calculate the invoice tax")
    docs = await embedder.embed_documents(
        [
            "def calc_tax(subtotal, region): return subtotal * rate_for(region)",
            "def render_text(invoice): return '\\n'.join(lines)",
            "class RateLimiter: def allow(self, key): bucket = self.store.get(key)",
        ]
    )
    scores = docs @ query
    assert int(np.argmax(scores)) == 0


async def test_camel_and_snake_case_share_features(embedder: CodeHashEmbedder) -> None:
    a = await embedder.embed_query("applyDiscount")
    b = await embedder.embed_query("apply_discount")
    assert float(a @ b) > 0.5


def test_features_include_subtokens() -> None:
    features = code_features("parseHttpResponse")
    assert any(f.startswith("pars") for f in features)
    assert any(f.startswith("respons") for f in features)


async def test_no_texts_gives_an_empty_matrix(embedder: CodeHashEmbedder) -> None:
    assert (await embedder.embed_documents([])).shape == (0, 384)


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        return [self.data.get(k) for k in keys]

    def pipeline(self, transaction: bool = False) -> _FakePipe:
        return _FakePipe(self)


class _FakePipe:
    def __init__(self, redis: _FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple[str, bytes]] = []

    async def __aenter__(self) -> _FakePipe:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.ops.append((key, value))

    async def execute(self) -> None:
        self.redis.data.update(self.ops)


class _Counting(CodeHashEmbedder):
    def __init__(self) -> None:
        super().__init__(64)
        self.calls = 0

    async def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        self.calls += len(texts)
        return await super().embed_documents(texts)


async def test_the_cache_serves_repeats_without_calling_the_model() -> None:
    inner = _Counting()
    cached = CachedEmbedder(inner, _FakeRedis(), 60)  # type: ignore[arg-type]
    first = await cached.embed_documents(["alpha beta", "gamma delta"])
    again = await cached.embed_documents(["alpha beta", "gamma delta", "new text"])
    assert inner.calls == 3
    assert np.allclose(first, again[:2])
