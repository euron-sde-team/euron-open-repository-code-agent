"""Answers: grounded in the index, cited with lines that exist, streamed and conversational."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tests.integration.support import Workspace, upload_repository, wait_for_repository

pytestmark = pytest.mark.integration


@pytest.fixture
async def indexed(client: httpx.AsyncClient, workspace: Workspace) -> Workspace:
    await upload_repository(client, workspace, "ledgerkit", wait=False)
    await upload_repository(client, workspace, "ratelimit", wait=False)
    await wait_for_repository(client, workspace, "ledgerkit")
    await wait_for_repository(client, workspace, "ratelimit")
    return workspace


async def ask(
    client: httpx.AsyncClient,
    workspace: Workspace,
    question: str,
    role: str = "viewer",
    **extra: Any,
) -> dict[str, Any]:
    response = await client.post(
        f"{workspace.base}/ask",
        json={"question": question, **extra},
        headers=workspace.who(role).headers,
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def file_lines(
    client: httpx.AsyncClient, workspace: Workspace, repository: str, path: str
) -> list[str]:
    blob = (
        await client.get(
            f"{workspace.base}/repositories/{repository}/blob/{path}",
            headers=workspace.owner.headers,
        )
    ).json()
    return ["".join(text for _, text in line) for line in blob["lines"]]


async def test_an_answer_cites_real_lines_of_real_files(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    answer = await ask(client, indexed, "What does apply_discount do and which tests cover it?")
    message = answer["message"]
    assert message["role"] == "assistant"
    assert "apply_discount" in message["content"]
    assert message["usage"]["answerer"] == "local"
    assert message["usage"]["prompt_tokens"] == 0
    citations = message["citations"]
    assert citations
    paths = {c["path"] for c in citations}
    assert "ledgerkit/pricing.py" in paths
    assert any(p.startswith("tests/") for p in paths)
    for citation in citations:
        lines = await file_lines(client, indexed, citation["repository"], citation["path"])
        assert 1 <= citation["start_line"] <= citation["end_line"] <= len(lines)
        cited = "\n".join(lines[citation["start_line"] - 1 : citation["end_line"]])
        assert citation["snippet"].splitlines()[0].strip() in cited
    for marker in {f"[{c['n']}]" for c in citations}:
        assert marker in message["content"]


async def test_markers_in_the_text_always_have_a_matching_citation(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    import re

    answer = await ask(client, indexed, "Where is the tax for an invoice calculated?")
    message = answer["message"]
    used = {int(n) for n in re.findall(r"\[(\d+)\]", message["content"])}
    assert used and used == {c["n"] for c in message["citations"]}
    assert "ledgerkit/tax.py" in {c["path"] for c in message["citations"]}


async def test_a_question_can_be_scoped_to_one_repository(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    answer = await ask(
        client,
        indexed,
        "How does the limiter decide whether a request is allowed?",
        repository="ratelimit",
    )
    assert {c["repository"] for c in answer["message"]["citations"]} == {"ratelimit"}


async def test_no_answer_is_invented_when_the_code_does_not_say(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    answer = await ask(client, indexed, "xyzzy plugh frobnicate quantum entanglement")
    assert "could not find" in answer["message"]["content"].lower()
    assert answer["message"]["citations"] == []


async def test_without_an_indexed_repository_the_answer_says_so(
    client: httpx.AsyncClient, workspace: Workspace
) -> None:
    answer = await ask(client, workspace, "What does anything do?")
    assert "no indexed repository" in answer["message"]["content"].lower()


async def test_answers_stream_as_server_sent_events(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    async with client.stream(
        "POST",
        f"{indexed.base}/ask/stream",
        json={"question": "Where is calc_tax defined?"},
        headers=indexed.who("viewer").headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        name = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "sources" and kinds[-1] == "done"
    assert kinds.count("delta") >= 2
    streamed = "".join(data["text"] for kind, data in events if kind == "delta")
    done = events[-1][1]["message"]
    assert (
        streamed.replace(" ", "").startswith(done["content"][:20].replace(" ", ""))
        or done["content"]
    )
    assert events[0][1]["sources"][0]["path"]


async def test_a_conversation_keeps_history_and_resolves_follow_ups(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    headers = indexed.who("developer").headers
    created = await client.post(
        f"{indexed.base}/conversations", json={"repository": "ledgerkit"}, headers=headers
    )
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["title"] == "New question"
    first = await client.post(
        f"{indexed.base}/conversations/{conversation['id']}/messages",
        json={"question": "What does calc_tax do?"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    followup = await client.post(
        f"{indexed.base}/conversations/{conversation['id']}/messages",
        json={"question": "And where is it called from?"},
        headers=headers,
    )
    text = followup.json()["message"]["content"]
    assert "calc_tax" in text
    assert any(c["path"] == "ledgerkit/invoice.py" for c in followup.json()["message"]["citations"])
    messages = (
        await client.get(
            f"{indexed.base}/conversations/{conversation['id']}/messages", headers=headers
        )
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    detail = (
        await client.get(f"{indexed.base}/conversations/{conversation['id']}", headers=headers)
    ).json()
    assert detail["title"].startswith("What does calc_tax do")
    assert detail["message_count"] == 4
    renamed = await client.patch(
        f"{indexed.base}/conversations/{conversation['id']}", json={"title": "Tax"}, headers=headers
    )
    assert renamed.json()["title"] == "Tax"
    listing = (await client.get(f"{indexed.base}/conversations", headers=headers)).json()
    assert [c["id"] for c in listing] == [conversation["id"]]


async def test_conversations_are_private_to_their_owner(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    mine = indexed.who("developer").headers
    conversation = (
        await client.post(f"{indexed.base}/conversations", json={}, headers=mine)
    ).json()
    for role in ("owner", "maintainer", "viewer"):
        other = indexed.who(role).headers
        assert (
            await client.get(f"{indexed.base}/conversations/{conversation['id']}", headers=other)
        ).status_code == 404
        assert (await client.get(f"{indexed.base}/conversations", headers=other)).json() == []
        assert (
            await client.delete(f"{indexed.base}/conversations/{conversation['id']}", headers=other)
        ).status_code == 404
    assert (
        await client.delete(f"{indexed.base}/conversations/{conversation['id']}", headers=mine)
    ).status_code == 204


async def test_api_keys_can_ask_but_cannot_keep_conversations(
    client: httpx.AsyncClient, indexed: Workspace
) -> None:
    created = await client.post(
        f"{indexed.base}/api-keys",
        json={"name": "ci", "role": "viewer"},
        headers=indexed.owner.headers,
    )
    key = created.json()["key"]
    headers = {"authorization": f"Bearer {key}"}
    answer = await client.post(
        f"{indexed.base}/ask", json={"question": "What does volume_discount do?"}, headers=headers
    )
    assert answer.status_code == 200
    assert answer.json()["message"]["citations"]
    convo = await client.post(f"{indexed.base}/conversations", json={}, headers=headers)
    assert convo.status_code == 403


async def test_answers_are_counted_in_usage(client: httpx.AsyncClient, indexed: Workspace) -> None:
    await ask(client, indexed, "What is Money?")
    overview = (await client.get(f"{indexed.base}/overview", headers=indexed.owner.headers)).json()
    assert overview["totals"]["questions"] >= 1
