"""Answerers: the offline local answerer and the model answerer, behind one interface.

Both stream text and fill in a `Usage`, so the ask service treats them the same way.

The local answerer does not generate language; it reads facts the index already holds
(signatures, docstrings, where a symbol is defined, who calls it, what it calls, which
tests exercise it) and composes them into a cited answer. It recognises five kinds of
question: where something is defined, what it does, who uses it, which tests cover it,
and open questions, which get the most relevant places in the code.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from codeagent.ai.chat import ChatClient, Usage
from codeagent.ai.prompts import Turn, answer_messages
from codeagent.ai.sources import CodeSource, Location, SymbolFacts
from codeagent.codeintel.terms import terms

NOT_FOUND = (
    "I could not find this in the indexed code. Try naming a function, class or file, "
    "or use code search to look for it directly."
)
_RETURN = re.compile(r"^\s*return\s+(.+?)\s*$", re.MULTILINE)


class Intent(StrEnum):
    DEFINITION = "definition"
    EXPLAIN = "explain"
    USAGES = "usages"
    TESTS = "tests"
    OVERVIEW = "overview"


def classify(question: str) -> Intent:
    q = question.lower()
    if re.search(
        r"\b(who|what|which|where)\b.*\b(calls?|uses?|invokes?|depends? on|imports?)\b", q
    ) or re.search(r"\b(usages?|callers?|called from|used by|references to|where is .* used)\b", q):
        return Intent.USAGES
    # "What does X do and which tests cover it?" is an explanation that includes the tests.
    asks_to_explain = re.search(r"\bwhat (does|do) \S+ do\b|\b(explain|describe)\b", q)
    if re.search(r"\b(tests?|tested|covered|coverage|specs?)\b", q) and not asks_to_explain:
        return Intent.TESTS
    if re.search(
        r"\bwhere\b.*\b(defined|declared|implemented|live|lives|located|is the code)\b", q
    ) or re.match(r"^\s*(find|locate|show me)\b", q):
        return Intent.DEFINITION
    if re.search(
        r"\b(what (does|do|is|are)|explain|how (does|do|is)|describe|purpose of)\b",
        q,
    ):
        return Intent.EXPLAIN
    return Intent.OVERVIEW


@dataclass(slots=True)
class AnswerRequest:
    question: str
    sources: list[CodeSource]
    facts: list[SymbolFacts] = field(default_factory=list)
    focus: list[uuid.UUID] = field(default_factory=list)
    history: list[Turn] = field(default_factory=list)


class Answerer(Protocol):
    label: str
    uses_model: bool
    # Bumped whenever answering changes, so stored answers record which version wrote them.
    version: str

    def stream(self, request: AnswerRequest, usage: Usage) -> AsyncIterator[str]: ...


def _lines(start: int, end: int) -> str:
    return f"line {start}" if start == end else f"lines {start} to {end}"


def _summary(fact: SymbolFacts, source: CodeSource | None) -> str:
    """The docstring, or what a short body returns, as one sentence."""
    if fact.doc:
        return fact.doc if fact.doc.endswith((".", "!", "?")) else f"{fact.doc}."
    if source is not None:
        match = _RETURN.search(source.text)
        if match and len(match.group(1)) <= 90:
            return f"It returns `{match.group(1)}`."
    return ""


class LocalAnswerer:
    label = "local"
    uses_model = False
    version = "1"

    async def stream(self, request: AnswerRequest, usage: Usage) -> AsyncIterator[str]:
        text = compose(request)
        # Emit line by line so the client renders this path like a model stream.
        for index, part in enumerate(text.split("\n")):
            yield part if index == 0 else "\n" + part
            await asyncio.sleep(0)


class _Writer:
    def __init__(self, request: AnswerRequest) -> None:
        self.sources = request.sources

    def source_for(self, path: str, line: int) -> CodeSource | None:
        return next((s for s in self.sources if s.contains(path, line)), None)

    def cite(self, path: str, line: int) -> str:
        source = self.source_for(path, line)
        return f" [{source.n}]" if source else ""

    def where(self, location: Location) -> str:
        cite = self.cite(location.path, location.line)
        return f"`{location.name}` in `{location.path}`, line {location.line}{cite}"

    def names(self, locations: list[Location], limit: int = 6) -> str:
        shown = [f"`{loc.name}`{self.cite(loc.path, loc.line)}" for loc in locations[:limit]]
        more = len(locations) - limit
        return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


def _focus(request: AnswerRequest) -> list[SymbolFacts]:
    by_id = {fact.symbol_id: fact for fact in request.facts}
    focused = [by_id[i] for i in request.focus if i in by_id]
    if focused:
        return focused
    for source in request.sources:
        if source.symbol_id in by_id:
            return [by_id[source.symbol_id]]
    return []


def _mentions_the_question(request: AnswerRequest) -> bool:
    """Whether any top source shares a word with the question (names, path or code)."""
    wanted = set(terms(request.question))
    if not wanted:
        return False
    for source in request.sources[:5]:
        haystack = f"{source.path} {source.qualified_name or ''} {source.text}"
        if wanted & set(terms(haystack)):
            return True
    return False


def compose(request: AnswerRequest) -> str:
    if not request.sources:
        return NOT_FOUND
    writer = _Writer(request)
    intent = classify(request.question)
    focus = _focus(request)
    if not request.focus and not _mentions_the_question(request):
        # Retrieval always returns the nearest chunks; being near is not being relevant.
        return NOT_FOUND
    if intent is not Intent.OVERVIEW and focus:
        fact = focus[0]
        if intent is Intent.USAGES:
            return _usages(writer, fact)
        if intent is Intent.TESTS:
            return _tests(writer, fact)
        if intent is Intent.DEFINITION:
            return _definitions(writer, focus)
        return _explain(writer, fact)
    return _overview(writer, request, focus)


def _definitions(writer: _Writer, facts: list[SymbolFacts]) -> str:
    fact = facts[0]
    same_name = [f for f in facts if f.name == fact.name]
    if len(same_name) > 1:
        lines = [f"`{fact.name}` is defined in {len(same_name)} places:", ""]
        lines += [
            f"- {f.kind} `{f.qualified_name}` in `{f.path}`, {_lines(f.start_line, f.end_line)}"
            f"{writer.cite(f.path, f.start_line)}"
            for f in same_name
        ]
        return "\n".join(lines)
    cite = writer.cite(fact.path, fact.start_line)
    out = [
        f"`{fact.name}` is a {fact.kind} defined in `{fact.path}`, "
        f"{_lines(fact.start_line, fact.end_line)}{cite}.",
    ]
    if fact.signature:
        out += ["", "```", fact.signature, "```"]
    summary = _summary(fact, writer.source_for(fact.path, fact.start_line))
    if summary:
        out += ["", f"{summary}{cite}"]
    return "\n".join(out)


def _explain(writer: _Writer, fact: SymbolFacts) -> str:
    source = writer.source_for(fact.path, fact.start_line)
    cite = writer.cite(fact.path, fact.start_line)
    summary = _summary(fact, source)
    head = (
        f"`{fact.qualified_name}` is a {fact.kind} in `{fact.path}` "
        f"({_lines(fact.start_line, fact.end_line)}){cite}."
    )
    out = [f"{head} {summary}".strip(), ""]
    if fact.signature:
        out.append(f"- **Signature:** `{fact.signature}`")
    if fact.callees:
        out.append(f"- **Calls:** {writer.names(fact.callees)}")
    if fact.callers:
        out.append(f"- **Called by:** {writer.names(fact.callers)}")
    if fact.tests:
        out.append(f"- **Tests:** {writer.names(fact.tests, limit=4)}")
    if not (fact.callers or fact.tests):
        out.append("- No callers or tests reference it in the indexed code.")
    return "\n".join(out).rstrip()


def _usages(writer: _Writer, fact: SymbolFacts) -> str:
    if not fact.callers:
        return (
            f"No callers of `{fact.name}` were found in the indexed code"
            f"{writer.cite(fact.path, fact.start_line)}. "
            "It may only be called dynamically, from tests, or from outside this repository."
        )
    count = len(fact.callers)
    lines = [f"`{fact.name}` is called from {count} place{'s' if count != 1 else ''}:", ""]
    lines += [f"- {writer.where(location)}" for location in fact.callers[:12]]
    if count > 12:
        lines.append(f"- and {count - 12} more")
    return "\n".join(lines)


def _tests(writer: _Writer, fact: SymbolFacts) -> str:
    if not fact.tests:
        return (
            f"No test references `{fact.name}` directly{writer.cite(fact.path, fact.start_line)}. "
            "It may still be exercised indirectly through the functions that call it."
        )
    count = len(fact.tests)
    lines = [f"`{fact.name}` is exercised by {count} test{'s' if count != 1 else ''}:", ""]
    lines += [f"- {writer.where(location)}" for location in fact.tests[:12]]
    return "\n".join(lines)


def _overview(writer: _Writer, request: AnswerRequest, focus: list[SymbolFacts]) -> str:
    question_terms = set(terms(request.question))
    by_symbol = {fact.symbol_id: fact for fact in request.facts}
    entries: list[str] = []
    lead = ""
    for source in request.sources[:5]:
        fact = by_symbol.get(source.symbol_id) if source.symbol_id else None
        name = source.qualified_name or source.symbol_name
        place = f"`{source.path}` ({_lines(source.start_line, source.end_line)}) [{source.n}]"
        summary = _summary(fact, source) if fact else ""
        entries.append(
            f"- **`{name}`** in {place}" + (f": {summary}" if summary else "")
            if name
            else f"- {place}"
        )
        if not lead and name and question_terms & set(terms(name.rsplit(".", 1)[-1])):
            lead = f"This is handled by `{name}` in `{source.path}` [{source.n}]."
    if not lead and focus:
        fact = focus[0]
        cite = writer.cite(fact.path, fact.start_line)
        lead = f"The closest match is `{fact.qualified_name}` in `{fact.path}`{cite}."
    header = lead or "The most relevant code for this question:"
    return "\n".join([header, "", *entries])


class ModelAnswerer:
    uses_model = True
    version = "1"

    def __init__(self, client: ChatClient) -> None:
        self.client = client
        self.label = f"{client.provider}:{client.model}"

    async def stream(self, request: AnswerRequest, usage: Usage) -> AsyncIterator[str]:
        if not request.sources:
            yield NOT_FOUND
            return
        messages = answer_messages(
            request.question, request.sources, request.facts, request.history
        )
        async for delta in self.client.stream(messages, usage):
            yield delta
