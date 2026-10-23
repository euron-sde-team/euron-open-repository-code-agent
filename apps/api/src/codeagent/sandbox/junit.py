"""Test results from JUnit XML (pytest, Jest, Go and most runners write it), or the log.

Parsed with defusedxml: the XML comes out of the sandbox and is as untrusted as the code
that produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_CASES = 2000
MAX_MESSAGE = 4000
_SUMMARY = re.compile(
    r"=+ (?P<body>[^=]*?\b(passed|failed|error|errors|skipped|no tests ran)\b[^=]*?) =+"
)
_COUNT = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")


@dataclass(slots=True)
class CaseResult:
    name: str
    classname: str
    status: str  # passed | failed | error | skipped
    duration_ms: int = 0
    message: str = ""
    file: str | None = None
    line: int | None = None

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "classname": self.classname,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "file": self.file,
            "line": self.line,
        }


@dataclass(slots=True)
class TestSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0


def _file_from_classname(classname: str) -> str | None:
    parts = [part for part in classname.split(".") if part]
    while parts and parts[-1][:1].isupper():
        parts.pop()  # TestDiscount: a class inside the module
    return "/".join(parts) + ".py" if parts else None


def _case(element: Element) -> CaseResult:
    name = element.get("name", "")
    classname = element.get("classname", "")
    try:
        duration_ms = int(float(element.get("time", "0")) * 1000)
    except ValueError:
        duration_ms = 0
    status, message = "passed", ""
    for tag, outcome in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
        child = element.find(tag)
        if child is not None:
            status = outcome
            text = (child.get("message") or "").strip()
            body = (child.text or "").strip()
            message = f"{text}\n\n{body}".strip() if body and body != text else text
            break
    file = element.get("file") or _file_from_classname(classname)
    line_attr = element.get("line")
    return CaseResult(
        name=name,
        classname=classname,
        status=status,
        duration_ms=duration_ms,
        message=message[:MAX_MESSAGE],
        file=file,
        line=int(line_attr) if line_attr and line_attr.isdigit() else None,
    )


def parse_junit(xml: bytes) -> TestSummary | None:
    try:
        root = ElementTree.fromstring(xml)
    except (ElementTree.ParseError, DefusedXmlException):
        return None
    summary = TestSummary()
    for element in root.iter("testcase"):
        case = _case(element)
        summary.total += 1
        if case.status == "passed":
            summary.passed += 1
        elif case.status == "failed":
            summary.failed += 1
        elif case.status == "error":
            summary.errors += 1
        else:
            summary.skipped += 1
        if len(summary.cases) < MAX_CASES:
            summary.cases.append(case)
    return summary


def parse_pytest_summary(log: str) -> TestSummary | None:
    """The `=== 1 failed, 24 passed in 0.31s ===` line, when there is no JUnit file."""
    matches = list(_SUMMARY.finditer(log))
    if not matches:
        return None
    counts = {kind: int(number) for number, kind in _COUNT.findall(matches[-1].group("body"))}
    summary = TestSummary(
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0),
        errors=counts.get("error", 0) + counts.get("errors", 0),
        skipped=counts.get("skipped", 0),
    )
    summary.total = summary.passed + summary.failed + summary.errors + summary.skipped
    return summary
