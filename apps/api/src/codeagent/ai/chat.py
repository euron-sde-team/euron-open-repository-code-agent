"""Chat model clients behind one interface, used by the model answerer and the model planner.

Two wire formats cover most providers: the OpenAI-compatible Chat Completions API (OpenAI,
Groq, Together, Mistral, DeepSeek, OpenRouter, vLLM, LM Studio and others) and Ollama's
native /api/chat. Both stream token deltas and report usage when the server does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx
import orjson

from codeagent.core.config import Settings
from codeagent.core.errors import UpstreamError
from codeagent.core.logging import get_logger

log = get_logger("codeagent.chat")
Messages = list[dict[str, str]]


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens

    def as_dict(self) -> dict[str, int]:
        return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


class ChatClient(Protocol):
    provider: str
    model: str

    def stream(self, messages: Messages, usage: Usage) -> AsyncIterator[str]: ...

    async def complete(
        self, messages: Messages, usage: Usage, max_tokens: int | None = None
    ) -> str: ...

    async def aclose(self) -> None: ...


class OpenAICompatibleClient:
    provider = "openai"

    def __init__(self, settings: Settings) -> None:
        self.model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"authorization": f"Bearer {key}"} if key else {},
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
        )

    async def stream(self, messages: Messages, usage: Usage) -> AsyncIterator[str]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as response:
                if response.status_code >= 400:
                    detail = (await response.aread())[:300].decode(errors="replace")
                    log.warning("llm_error", status=response.status_code, detail=detail)
                    raise UpstreamError(f"The model provider returned HTTP {response.status_code}.")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    event = orjson.loads(payload)
                    if event.get("usage"):
                        usage.prompt_tokens = event["usage"].get("prompt_tokens", 0)
                        usage.completion_tokens = event["usage"].get("completion_tokens", 0)
                    for choice in event.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            yield delta
        except httpx.TimeoutException as exc:
            raise UpstreamError("The model provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("The model provider could not be reached.") from exc

    async def complete(
        self, messages: Messages, usage: Usage, max_tokens: int | None = None
    ) -> str:
        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": self._temperature,
                    "max_tokens": max_tokens or self._max_tokens,
                },
            )
        except httpx.TimeoutException as exc:
            raise UpstreamError("The model provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("The model provider could not be reached.") from exc
        if response.status_code >= 400:
            log.warning("llm_error", status=response.status_code, detail=response.text[:300])
            raise UpstreamError(f"The model provider returned HTTP {response.status_code}.")
        body = response.json()
        reported = body.get("usage") or {}
        usage.prompt_tokens += int(reported.get("prompt_tokens", 0))
        usage.completion_tokens += int(reported.get("completion_tokens", 0))
        content: str = body["choices"][0]["message"].get("content") or ""
        return content

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaClient:
    provider = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.model = settings.llm_model
        self._options = {
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_max_tokens,
        }
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/"),
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
        )

    async def stream(self, messages: Messages, usage: Usage) -> AsyncIterator[str]:
        body = {"model": self.model, "messages": messages, "stream": True, "options": self._options}
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as response:
                if response.status_code >= 400:
                    raise UpstreamError(f"Ollama returned HTTP {response.status_code}.")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = orjson.loads(line)
                    delta = (event.get("message") or {}).get("content")
                    if delta:
                        yield delta
                    if event.get("done"):
                        usage.prompt_tokens = event.get("prompt_eval_count", 0)
                        usage.completion_tokens = event.get("eval_count", 0)
        except httpx.TimeoutException as exc:
            raise UpstreamError("Ollama timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("Ollama could not be reached.") from exc

    async def complete(
        self, messages: Messages, usage: Usage, max_tokens: int | None = None
    ) -> str:
        options = dict(self._options)
        if max_tokens:
            options["num_predict"] = max_tokens
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": options,
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise UpstreamError("Ollama timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("The Ollama request failed.") from exc
        body = response.json()
        usage.prompt_tokens += int(body.get("prompt_eval_count", 0))
        usage.completion_tokens += int(body.get("eval_count", 0))
        content: str = body["message"]["content"]
        return content

    async def aclose(self) -> None:
        await self._client.aclose()


def build_chat_client(settings: Settings) -> ChatClient | None:
    if settings.llm_provider == "openai":
        return OpenAICompatibleClient(settings)
    if settings.llm_provider == "ollama":
        return OllamaClient(settings)
    return None


def estimate_tokens(text: str) -> int:
    """Four characters per token: close enough for budgets, and the same everywhere."""
    return (len(text) + 3) // 4 if text else 0
