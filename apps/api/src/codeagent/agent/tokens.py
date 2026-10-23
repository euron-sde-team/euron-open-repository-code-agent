"""A small, language-neutral token stream for precise source edits.

Python is tokenized with the standard library `tokenize` (exact, including f-strings);
other languages with Pygments. Positions are character offsets within a line, so edits can
be applied from right to left without disturbing anything else on the line.
"""

from __future__ import annotations

import io
import tokenize
from dataclasses import dataclass

from pygments.token import Name, Operator, Punctuation, String, _TokenType

from codeagent.codeintel.highlight import lexer_for


@dataclass(frozen=True, slots=True)
class Tok:
    kind: str  # name | string | op | other
    text: str
    line: int  # 1-based
    start: int
    end: int


class TokenizeError(Exception):
    pass


def python_tokens(source: str) -> list[Tok]:
    tokens: list[Tok] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                kind = "name"
            elif token.type == tokenize.STRING:
                kind = "string"
            elif token.type == tokenize.OP:
                kind = "op"
            else:
                kind = "other"
            (row, col), (end_row, end_col) = token.start, token.end
            if row == end_row:
                tokens.append(Tok(kind, token.string, row, col, end_col))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise TokenizeError(str(exc)) from exc
    return tokens


def _within(token_type: _TokenType, parent: _TokenType) -> bool:
    current: _TokenType | None = token_type
    while current is not None:
        if current is parent:
            return True
        current = current.parent
    return False


def generic_tokens(source: str, language: str, path: str) -> list[Tok]:
    tokens: list[Tok] = []
    line, col = 1, 0
    for token_type, value in lexer_for(language, path).get_tokens(source):
        parts = value.split("\n")
        if len(parts) == 1:
            if _within(token_type, Name):
                kind = "name"
            elif _within(token_type, String):
                kind = "string"
            elif _within(token_type, Punctuation) or _within(token_type, Operator):
                kind = "op"
            else:
                kind = "other"
            tokens.append(Tok(kind, value, line, col, col + len(value)))
            col += len(value)
        else:
            line += len(parts) - 1
            col = len(parts[-1])
    return tokens


def tokens_for(source: str, language: str, path: str) -> list[Tok]:
    if language == "Python":
        return python_tokens(source)
    return generic_tokens(source, language, path)


def apply_replacements(source: str, replacements: list[tuple[Tok, str]]) -> str:
    """Replace each token's text, right to left within each line."""
    if not replacements:
        return source
    lines = source.splitlines(keepends=True)
    by_line: dict[int, list[tuple[Tok, str]]] = {}
    for tok, text in replacements:
        by_line.setdefault(tok.line, []).append((tok, text))
    for number, items in by_line.items():
        current = lines[number - 1]
        for tok, text in sorted(items, key=lambda item: item[0].start, reverse=True):
            current = current[: tok.start] + text + current[tok.end :]
        lines[number - 1] = current
    return "".join(lines)
