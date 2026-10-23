"""File classification: language, test or not, vendored or not, text or binary.

Language names are the display names used across the API and the web app. The extension
table covers what most repositories contain; anything else is still indexed as text.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

PYTHON = "Python"
JAVASCRIPT = "JavaScript"
TYPESCRIPT = "TypeScript"
TSX = "TSX"
GO = "Go"
TEXT = "Text"

_EXTENSIONS: dict[str, str] = {
    ".py": PYTHON,
    ".pyi": PYTHON,
    ".js": JAVASCRIPT,
    ".mjs": JAVASCRIPT,
    ".cjs": JAVASCRIPT,
    ".jsx": JAVASCRIPT,
    ".ts": TYPESCRIPT,
    ".mts": TYPESCRIPT,
    ".cts": TYPESCRIPT,
    ".tsx": TSX,
    ".go": GO,
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".hpp": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".tf": "HCL",
    ".proto": "Protocol Buffers",
    ".txt": TEXT,
}
_FILENAMES: dict[str, str] = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "Gemfile": "Ruby",
    "Rakefile": "Ruby",
    "Jenkinsfile": "Groovy",
}
_SHEBANGS: tuple[tuple[str, str], ...] = (
    ("python", PYTHON),
    ("node", JAVASCRIPT),
    ("bash", "Shell"),
    ("/sh", "Shell"),
)
# Directories that hold third-party or generated code: indexing them buries the project's
# own code in search results and wastes the index budget.
_VENDORED_DIRS = frozenset(
    {
        "node_modules",
        "vendor",
        "third_party",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        "coverage",
        ".tox",
        ".terraform",
    }
)
_GENERATED = re.compile(r"(\.min\.(js|css)|\.map|\.lock|-lock\.json|\.pb\.go|_pb2\.py)$")
_TEST_FILE = re.compile(
    r"(^|/)(test_[^/]+\.py|[^/]+_test\.(py|go)|[^/]+\.(test|spec)\.(js|jsx|ts|tsx|mjs))$"
)
_TEST_DIR = re.compile(r"(^|/)(tests?|__tests__|spec)/")

# Languages with a symbol extractor; everything else is chunked and searched as text.
STRUCTURED = frozenset({PYTHON, JAVASCRIPT, TYPESCRIPT, TSX, GO})


def detect_language(path: str, head: str = "") -> str:
    pure = PurePosixPath(path)
    if pure.name in _FILENAMES:
        return _FILENAMES[pure.name]
    language = _EXTENSIONS.get(pure.suffix.lower())
    if language:
        return language
    if head.startswith("#!"):
        first_line = head.split("\n", 1)[0]
        for marker, name in _SHEBANGS:
            if marker in first_line:
                return name
    return TEXT


def is_vendored(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return any(part in _VENDORED_DIRS for part in parts[:-1]) or bool(_GENERATED.search(path))


def is_test_path(path: str) -> bool:
    return bool(_TEST_FILE.search(path) or _TEST_DIR.search(path))


def looks_binary(head: bytes) -> bool:
    """A NUL byte in the first 8 KB is how git itself decides a file is binary."""
    return b"\x00" in head[:8192]
