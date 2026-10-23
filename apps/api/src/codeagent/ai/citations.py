"""Turn [n] markers in an answer into verified citations of files and line ranges.

Markers that point at a source the answer was not given are removed rather than shown, so
a citation is never a dead link. Each kept citation carries the repository, the path, the
line range and the first lines of the cited code for the hover preview.
"""

from __future__ import annotations

import re
from typing import Any

from codeagent.ai.sources import CodeSource

_MARKER = re.compile(r"\s?\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]")


def _numbers(group: str) -> list[int]:
    return [int(part) for part in re.split(r"[,;]\s*", group) if part.strip().isdigit()]


def extract_citations(answer: str, sources: list[CodeSource]) -> tuple[str, list[dict[str, Any]]]:
    by_number = {s.n: s for s in sources}
    used: list[int] = []

    def keep_valid(match: re.Match[str]) -> str:
        valid = [n for n in _numbers(match.group(1)) if n in by_number]
        used.extend(valid)
        return "".join(f" [{n}]" for n in dict.fromkeys(valid))

    # Code blocks are left alone: `items[1]` in a snippet is an index, not a citation.
    parts = re.split(r"(```.*?```)", answer, flags=re.DOTALL)
    cleaned = "".join(
        part if part.startswith("```") else _MARKER.sub(keep_valid, part) for part in parts
    )

    citations = []
    for n in sorted(set(used)):
        source = by_number[n]
        citations.append(
            {
                "n": n,
                "repository_id": str(source.repository_id),
                "repository": source.repository,
                "file_id": str(source.file_id),
                "path": source.path,
                "start_line": source.start_line,
                "end_line": source.end_line,
                "symbol": source.qualified_name or source.symbol_name,
                "snippet": source.snippet(8),
            }
        )
    return cleaned.strip(), citations
