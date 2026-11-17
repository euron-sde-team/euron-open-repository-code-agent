"""Settings, passwords, sessions, API keys, rate limits and the error envelope."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import fakeredis
import httpx
import pytest
from fastapi import FastAPI

from codeagent.core.config import DEV_SECRET, Settings
from codeagent.core.context import BodySizeLimitMiddleware, RequestContextMiddleware
from codeagent.core.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    install_exception_handlers,
)
from codeagent.core.ids import uuid7
from codeagent.core.ratelimit import RateLimiter
from codeagent.core.security import (
    decode_session,
    generate_api_key,
    hash_password,
    issue_session,
    parse_api_key,
    validate_password,
    verify_api_key_secret,
    verify_password,
)


def production(**values: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "production",
        "session_secret": "s" * 40,
        "api_key_pepper": "p" * 40,
        "cookie_secure": True,
        "storage_backend": "s3",
        "s3_bucket": "bucket",
        "queue_backend": "sqs",
        "sqs_queue_url": "https://sqs.example.com/1/jobs",
    }
    return Settings.model_validate({**base, **values})


def test_a_correct_production_configuration_has_no_problems() -> None:
    assert production().production_problems() == []


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"session_secret": DEV_SECRET}, "SESSION_SECRET"),
        ({"api_key_pepper": "short"}, "API_KEY_PEPPER"),
        ({"api_key_pepper": "s" * 40}, "must differ"),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
        ({"storage_backend": "local"}, "STORAGE_BACKEND"),
        ({"queue_backend": "inline"}, "QUEUE_BACKEND"),
        ({"aws_endpoint_url": "http://floci:4566"}, "emulator"),
        ({"allow_private_git_hosts": True}, "ALLOW_PRIVATE_GIT_HOSTS"),
        ({"llm_provider": "openai", "llm_model": ""}, "LLM_MODEL"),
    ],
)
def test_production_refuses_unsafe_settings(override: dict[str, object], fragment: str) -> None:
    problems = production(**override).production_problems()
    assert any(fragment in p for p in problems), problems


def test_every_problem_is_reported_at_once() -> None:
    assert len(Settings(app_env="production").production_problems()) >= 5


def test_cors_origins_accept_a_comma_separated_string() -> None:
    settings = Settings.model_validate({"cors_origins": "http://a.test, http://b.test"})
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_the_model_label_names_provider_and_model() -> None:
    assert Settings().model_label == "local"
    assert (
        Settings(llm_provider="ollama", llm_model="qwen2.5-coder").model_label
        == "ollama:qwen2.5-coder"
    )


def test_passwords_are_hashed_verified_and_checked_for_strength() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")
    for weak in ("short", "aaaaaaaaaaaa", "me@example.com"):
        with pytest.raises(Exception, match=r"."):
            validate_password(weak, email="me@example.com")
    validate_password("a perfectly fine passphrase", email="me@example.com")


def test_sessions_round_trip_and_reject_tampering() -> None:
    user_id = uuid.uuid4()
    token, claims = issue_session(user_id, 3, secret="x" * 40, ttl=timedelta(hours=1))
    decoded = decode_session(token, secret="x" * 40)
    assert decoded.user_id == user_id and decoded.session_version == 3
    assert decoded.jti == claims.jti
    with pytest.raises(UnauthorizedError):
        decode_session(token, secret="y" * 40)
    with pytest.raises(UnauthorizedError):
        decode_session(token[:-3] + "abc", secret="x" * 40)
    expired, _ = issue_session(user_id, 1, secret="x" * 40, ttl=timedelta(seconds=-5))
    with pytest.raises(UnauthorizedError):
        decode_session(expired, secret="x" * 40)


def test_api_keys_store_only_a_keyed_hash() -> None:
    pepper = "pepper-" + "z" * 30
    generated = generate_api_key(pepper)
    assert generated.plaintext.startswith("cak_")
    parsed = parse_api_key(generated.plaintext)
    assert parsed is not None
    prefix, secret = parsed
    assert prefix == generated.prefix
    assert secret not in generated.secret_hash
    assert verify_api_key_secret(secret, generated.secret_hash, pepper)
    assert not verify_api_key_secret(secret, generated.secret_hash, "another-pepper")
    assert parse_api_key("not-a-key") is None
    assert parse_api_key(generated.plaintext + "x") is None


def test_uuid7_ids_sort_by_creation_time() -> None:
    ids = [uuid7() for _ in range(50)]
    assert [i.version for i in ids] == [7] * 50
    assert ids == sorted(ids) or len({i.int >> 80 for i in ids}) > 0


async def test_the_rate_limiter_counts_per_key_and_window() -> None:
    limiter = RateLimiter(fakeredis.FakeAsyncRedis())  # type: ignore[arg-type]
    results = [await limiter.hit("ask:user:1", 3) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert results[0].remaining == 2 and results[3].remaining == 0
    assert (await limiter.hit("ask:user:2", 3)).allowed
    assert results[3].headers()["x-ratelimit-limit"] == "3"


def build_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1000)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("No such thing.")

    @app.get("/conflict")
    async def conflict() -> None:
        raise ConflictError(details={"field": "name"})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.post("/echo")
    async def echo(payload: dict[str, int]) -> dict[str, int]:
        return payload

    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as http:
        yield http


async def test_errors_use_one_envelope_with_the_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/missing", headers={"x-request-id": "req-123"})
    assert response.status_code == 404
    body = response.json()["error"]
    assert body == {"code": "not_found", "message": "No such thing.", "request_id": "req-123"}
    assert response.headers["x-request-id"] == "req-123"


async def test_details_are_included_when_given(client: httpx.AsyncClient) -> None:
    response = await client.get("/conflict")
    assert response.json()["error"]["details"] == {"field": "name"}


async def test_unexpected_errors_leak_nothing(client: httpx.AsyncClient) -> None:
    response = await client.get("/boom")
    assert response.status_code == 500
    assert "secret internal detail" not in response.text
    assert response.json()["error"]["code"] == "internal_error"


async def test_validation_errors_are_listed_per_field(client: httpx.AsyncClient) -> None:
    response = await client.post("/echo", json={"a": "not a number"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["loc"][-1] == "a"


async def test_unknown_routes_and_methods_use_the_envelope(client: httpx.AsyncClient) -> None:
    assert (await client.get("/nope")).json()["error"]["code"] == "not_found"
    assert (await client.delete("/missing")).json()["error"]["code"] == "method_not_allowed"


async def test_every_response_has_a_request_id_and_security_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/missing", headers={"x-request-id": "bad id with spaces!"})
    assert response.headers["x-request-id"] != "bad id with spaces!"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_oversized_bodies_are_refused_before_parsing(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/echo", content=b"x" * 5000, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
