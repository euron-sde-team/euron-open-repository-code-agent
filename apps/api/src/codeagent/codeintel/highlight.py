"""Server-side syntax highlighting with Pygments, as line-level token lists.

The API returns, for every line, a list of `[class, text]` pairs. Classes are a dozen
stable names the web app styles with CSS tokens for both themes, so the browser needs no
highlighter and every language Pygments knows is covered. Text is never interpreted as
markup by the client: it renders spans with text nodes only.
"""

from __future__ import annotations

from functools import cache

from pygments.lexer import Lexer
from pygments.lexers import TextLexer, get_lexer_by_name, get_lexer_for_filename
from pygments.token import (
    Comment,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Token,
    _TokenType,
)
from pygments.util import ClassNotFound

Line = list[tuple[str, str]]
MAX_HIGHLIGHT_LINES = 6000
MAX_HIGHLIGHT_CHARS = 600_000

_LEXER_NAMES = {
    "Python": "python",
    "JavaScript": "javascript",
    "TypeScript": "typescript",
    "TSX": "tsx",
    "Go": "go",
    "Rust": "rust",
    "Java": "java",
    "Kotlin": "kotlin",
    "Ruby": "ruby",
    "PHP": "php",
    "C#": "csharp",
    "C": "c",
    "C++": "cpp",
    "Shell": "bash",
    "SQL": "sql",
    "HTML": "html",
    "CSS": "css",
    "SCSS": "scss",
    "Markdown": "markdown",
    "JSON": "json",
    "YAML": "yaml",
    "TOML": "toml",
    "INI": "ini",
    "HCL": "terraform",
    "Dockerfile": "docker",
    "Makefile": "make",
}

# Most specific first: the first prefix a token type falls under decides its class.
_CLASSES: tuple[tuple[_TokenType, str], ...] = (
    (Comment, "com"),
    (String.Doc, "doc"),
    (String, "str"),
    (Number, "num"),
    (Keyword.Type, "ty"),
    (Keyword, "kw"),
    (Operator.Word, "kw"),
    (Operator, "op"),
    (Punctuation, "punc"),
    (Name.Function, "fn"),
    (Name.Class, "cls"),
    (Name.Namespace, "ns"),
    (Name.Builtin, "bi"),
    (Name.Decorator, "dec"),
    (Name.Tag, "tag"),
    (Name.Attribute, "attr"),
    (Name.Constant, "const"),
    (Name.Variable, "var"),
    (Generic.Inserted, "ins"),
    (Generic.Deleted, "del"),
    (Generic.Heading, "kw"),
    (Generic.Subheading, "kw"),
)


@cache
def _class_for(token_type: _TokenType) -> str:
    for prefix, name in _CLASSES:
        current: _TokenType | None = token_type
        while current is not None:
            if current is prefix:
                return name
            current = current.parent
    return ""


@cache
def _lexer_by_name(name: str) -> Lexer:
    return get_lexer_by_name(name, stripnl=False, ensurenl=False, stripall=False)


def lexer_for(language: str, path: str) -> Lexer:
    name = _LEXER_NAMES.get(language)
    if name:
        try:
            return _lexer_by_name(name)
        except ClassNotFound:
            pass
    try:
        lexer: Lexer = get_lexer_for_filename(path, stripnl=False, ensurenl=False)
    except ClassNotFound:
        plain: Lexer = TextLexer(stripnl=False, ensurenl=False)
        return plain
    return lexer


def highlight_lines(text: str, language: str, path: str) -> list[Line]:
    """Every line of `text` as merged `(class, text)` runs; plain runs for huge files."""
    if len(text) > MAX_HIGHLIGHT_CHARS or text.count("\n") > MAX_HIGHLIGHT_LINES:
        return [[("", line)] if line else [] for line in text.split("\n")]
    lines: list[Line] = [[]]
    for token_type, value in lexer_for(language, path).get_tokens(text):
        css = _class_for(token_type) if token_type is not Token.Text else ""
        pieces = value.split("\n")
        for index, piece in enumerate(pieces):
            if index > 0:
                lines.append([])
            if not piece:
                continue
            current = lines[-1]
            if current and current[-1][0] == css:
                current[-1] = (css, current[-1][1] + piece)
            else:
                current.append((css, piece))
    # A trailing newline produces one empty line that is not part of the file's content.
    if text.endswith("\n") and lines and not lines[-1]:
        lines.pop()
    return lines
