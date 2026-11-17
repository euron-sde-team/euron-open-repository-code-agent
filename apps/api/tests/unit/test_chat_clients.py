"""The model adapters speak the real wire formats; respx plays the server."""

from __future__ import annotations

import httpx
import pytest
import respx

from codeagent.ai.chat import OllamaClient, OpenAICompatibleClient, Usage, build_chat_client
from codeagent.core.config import Settings
from codeagent.core.errors import UpstreamError


def settings(**values: object) -> Settings:
    base: dict[str, object] = {
        "llm_provider": "openai",
        "llm_model": "test-model",
        "llm_base_url": "http://llm.test/v1",
        "ollama_url": "http://ollama.test",
    }
    return Settings.model_validate({**base, **values})


SSE = (
    'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
    'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":2}}\n\n'
    "data: [DONE]\n\n"
)


@respx.mock
async def test_openai_compatible_streams_deltas_and_usage() -> None:
    route = respx.post("http://llm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=SSE, headers={"content-type": "text/event-stream"})
    )
    client = OpenAICompatibleClient(settings(llm_api_key="sk-test"))
    usage = Usage()
    parts = [p async for p in client.stream([{"role": "user", "content": "hi"}], usage)]
    assert "".join(parts) == "Hello world"
    assert (usage.prompt_tokens, usage.completion_tokens) == (12, 2)
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer sk-test"
    assert b'"stream":true' in request.content.replace(b" ", b"")
    await client.aclose()


@respx.mock
async def test_openai_compatible_complete_reads_the_message() -> None:
    respx.post("http://llm.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "PLAN: x"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        )
    )
    client = OpenAICompatibleClient(settings())
    usage = Usage()
    assert await client.complete([{"role": "user", "content": "go"}], usage) == "PLAN: x"
    assert usage.as_dict()["prompt_tokens"] == 5
    await client.aclose()


@respx.mock
async def test_provider_errors_become_upstream_errors() -> None:
    respx.post("http://llm.test/v1/chat/completions").mock(return_value=httpx.Response(429))
    client = OpenAICompatibleClient(settings())
    with pytest.raises(UpstreamError, match="429"):
        _ = [p async for p in client.stream([], Usage())]
    with pytest.raises(UpstreamError):
        await client.complete([], Usage())
    await client.aclose()


@respx.mock
async def test_an_unreachable_provider_is_reported_without_a_traceback() -> None:
    respx.post("http://llm.test/v1/chat/completions").mock(side_effect=httpx.ConnectError("no"))
    client = OpenAICompatibleClient(settings())
    with pytest.raises(UpstreamError, match="could not be reached"):
        _ = [p async for p in client.stream([], Usage())]
    await client.aclose()


@respx.mock
async def test_ollama_streams_ndjson() -> None:
    body = (
        '{"message":{"content":"Hi"},"done":false}\n'
        '{"message":{"content":" there"},"done":false}\n'
        '{"done":true,"prompt_eval_count":9,"eval_count":4}\n'
    )
    respx.post("http://ollama.test/api/chat").mock(return_value=httpx.Response(200, text=body))
    client = OllamaClient(settings(llm_provider="ollama"))
    usage = Usage()
    assert "".join([p async for p in client.stream([], usage)]) == "Hi there"
    assert (usage.prompt_tokens, usage.completion_tokens) == (9, 4)
    await client.aclose()


def test_the_provider_setting_picks_the_client() -> None:
    assert build_chat_client(settings(llm_provider="none")) is None
    assert isinstance(build_chat_client(settings(llm_provider="openai")), OpenAICompatibleClient)
    assert isinstance(build_chat_client(settings(llm_provider="ollama")), OllamaClient)
