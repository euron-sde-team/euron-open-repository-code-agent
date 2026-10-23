"""The offline planner's catalog of common helpers, each with an implementation and tests.

Without a model, CodeAgent cannot write arbitrary code, but it can add well-known helpers
correctly: placed in the right module, imported, exported, and covered by tests that run
in the sandbox before anyone reviews them. `__NAME__` stands for the name the task asked
for, so `add a percentage helper` and `add percent_of` get the same, correctly named code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Helper:
    name: str
    aliases: tuple[str, ...]
    summary: str
    imports: tuple[str, ...]
    source: str
    test_imports: tuple[str, ...]
    tests: str

    def render_source(self, name: str) -> str:
        return self.source.replace("__NAME__", name).strip("\n") + "\n"

    def render_tests(self, name: str) -> str:
        return self.tests.replace("__NAME__", name).strip("\n") + "\n"


HELPERS: tuple[Helper, ...] = (
    Helper(
        name="round_half_up",
        aliases=("round_money", "round_half_away", "round_currency"),
        summary="Round a decimal amount with halves going up, the way people expect for money.",
        imports=("from decimal import ROUND_HALF_UP, Decimal",),
        source='''
def __NAME__(value: Decimal | float | int | str, places: int = 2) -> Decimal:
    """Round `value` to `places` decimals, halves away from zero (2.675 -> 2.68).

    Python's round() and Decimal's default context use banker's rounding (2.5 -> 2), which
    surprises anyone reading an invoice. Floats are converted through str() so the result
    matches the number as written, not its binary approximation.
    """
    quantum = Decimal(1).scaleb(-places)
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
''',
        test_imports=("from decimal import Decimal",),
        tests="""
def test___NAME___rounds_halves_up():
    assert __NAME__(Decimal("2.675")) == Decimal("2.68")
    assert __NAME__("0.125") == Decimal("0.13")


def test___NAME___rounds_halves_away_from_zero_when_negative():
    assert __NAME__(Decimal("-1.005")) == Decimal("-1.01")


def test___NAME___supports_other_precisions():
    assert __NAME__(2.5, places=0) == Decimal("3")
    assert __NAME__(Decimal("1.23456"), places=3) == Decimal("1.235")
""",
    ),
    Helper(
        name="percent_of",
        aliases=("percent", "percentage", "percentage_of", "pct"),
        summary="Express a part as a percentage of a whole.",
        imports=(),
        source='''
def __NAME__(part: float, whole: float, places: int = 2) -> float:
    """`part` as a percentage of `whole`, rounded to `places` decimals; 0.0 when `whole` is 0."""
    if whole == 0:
        return 0.0
    return round(part / whole * 100, places)
''',
        test_imports=(),
        tests="""
def test___NAME___of_a_whole():
    assert __NAME__(1, 4) == 25.0
    assert __NAME__(1, 3) == 33.33


def test___NAME___of_zero_is_zero():
    assert __NAME__(5, 0) == 0.0
""",
    ),
    Helper(
        name="clamp",
        aliases=("bound", "constrain", "clamp_value"),
        summary="Limit a value to a closed range.",
        imports=(),
        source='''
def __NAME__(value: float, low: float, high: float) -> float:
    """Limit `value` to the closed range [`low`, `high`]."""
    if low > high:
        raise ValueError("low must not be greater than high")
    return max(low, min(value, high))
''',
        test_imports=("import pytest",),
        tests="""
def test___NAME___keeps_values_inside_the_range():
    assert __NAME__(5, 0, 10) == 5


def test___NAME___limits_values_outside_the_range():
    assert __NAME__(-3, 0, 10) == 0
    assert __NAME__(42, 0, 10) == 10


def test___NAME___rejects_an_empty_range():
    with pytest.raises(ValueError):
        __NAME__(1, 10, 0)
""",
    ),
    Helper(
        name="slugify",
        aliases=("slug", "to_slug", "make_slug"),
        summary="Turn text into a lowercase ASCII slug for URLs and file names.",
        imports=("import re", "import unicodedata"),
        source='''
def __NAME__(text: str, separator: str = "-") -> str:
    """Lowercase ASCII words of `text` joined by `separator`, for URLs and file names."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return separator.join(re.findall(r"[a-z0-9]+", normalized.lower()))
''',
        test_imports=(),
        tests="""
def test___NAME___lowercases_and_joins_words():
    assert __NAME__("Hello, World!") == "hello-world"


def test___NAME___collapses_spaces_and_punctuation():
    assert __NAME__("  Q3 -- Invoice   #42  ") == "q3-invoice-42"


def test___NAME___uses_the_given_separator():
    assert __NAME__("Release notes 4.2", separator="_") == "release_notes_4_2"
""",
    ),
    Helper(
        name="chunked",
        aliases=("chunks", "batched", "batch", "split_into_chunks"),
        summary="Split a sequence into lists of at most n items.",
        imports=("from collections.abc import Sequence", "from typing import Any"),
        source='''
def __NAME__(items: Sequence[Any], size: int) -> list[list[Any]]:
    """`items` in consecutive lists of at most `size` elements, in order."""
    if size < 1:
        raise ValueError("size must be at least 1")
    return [list(items[start : start + size]) for start in range(0, len(items), size)]
''',
        test_imports=("import pytest",),
        tests="""
def test___NAME___splits_in_order():
    assert __NAME__([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test___NAME___of_nothing_is_empty():
    assert __NAME__([], 3) == []


def test___NAME___rejects_a_size_below_one():
    with pytest.raises(ValueError):
        __NAME__([1], 0)
""",
    ),
    Helper(
        name="safe_divide",
        aliases=("safe_div", "divide_or_default", "div_or_zero"),
        summary="Divide, returning a default instead of raising on a zero denominator.",
        imports=(),
        source='''
def __NAME__(numerator: float, denominator: float, default: float = 0.0) -> float:
    """`numerator / denominator`, or `default` when the denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator
''',
        test_imports=(),
        tests="""
def test___NAME___divides():
    assert __NAME__(10, 4) == 2.5


def test___NAME___returns_the_default_for_zero():
    assert __NAME__(1, 0) == 0.0
    assert __NAME__(1, 0, default=-1) == -1
""",
    ),
    Helper(
        name="median",
        aliases=("median_of", "middle_value"),
        summary="The median of a non-empty collection of numbers.",
        imports=("from collections.abc import Iterable",),
        source='''
def __NAME__(values: Iterable[float]) -> float:
    """The middle value (the mean of the two middle values for an even count)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median of an empty collection")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2
''',
        test_imports=("import pytest",),
        tests="""
def test___NAME___of_an_odd_count():
    assert __NAME__([3, 1, 2]) == 2


def test___NAME___of_an_even_count():
    assert __NAME__([4, 1, 3, 2]) == 2.5


def test___NAME___of_nothing_raises():
    with pytest.raises(ValueError):
        __NAME__([])
""",
    ),
    Helper(
        name="parse_bool",
        aliases=("to_bool", "str_to_bool", "parse_boolean", "as_bool"),
        summary="Parse yes/no style text into a boolean.",
        imports=(),
        source='''
def __NAME__(value: str | bool | int) -> bool:
    """True for 1/true/yes/on, False for 0/false/no/off/empty; anything else is an error."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off", ""}:
        return False
    raise ValueError(f"not a boolean: {value!r}")
''',
        test_imports=("import pytest",),
        tests="""
def test___NAME___accepts_common_spellings():
    assert __NAME__("Yes") is True
    assert __NAME__(" off ") is False
    assert __NAME__(1) is True


def test___NAME___rejects_anything_else():
    with pytest.raises(ValueError):
        __NAME__("maybe")
""",
    ),
    Helper(
        name="truncate",
        aliases=("shorten", "ellipsize", "truncate_text"),
        summary="Shorten text to a maximum length with a suffix.",
        imports=(),
        source='''
def __NAME__(text: str, limit: int, suffix: str = "...") -> str:
    """`text` cut to at most `limit` characters, ending in `suffix` when it was cut."""
    if limit < len(suffix):
        raise ValueError("limit must leave room for the suffix")
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)].rstrip() + suffix
''',
        test_imports=("import pytest",),
        tests="""
def test___NAME___keeps_short_text():
    assert __NAME__("short", 10) == "short"


def test___NAME___cuts_long_text_with_a_suffix():
    assert __NAME__("The quick brown fox", 12) == "The quick..."


def test___NAME___needs_room_for_the_suffix():
    with pytest.raises(ValueError):
        __NAME__("text", 2)
""",
    ),
    Helper(
        name="dedupe",
        aliases=("unique", "deduplicate", "unique_everseen", "distinct"),
        summary="Remove duplicates while keeping the first occurrence order.",
        imports=("from collections.abc import Hashable, Iterable",),
        source='''
def __NAME__(items: Iterable[Hashable]) -> list[Hashable]:
    """`items` without repeats, in the order each was first seen."""
    return list(dict.fromkeys(items))
''',
        test_imports=(),
        tests="""
def test___NAME___keeps_first_occurrences_in_order():
    assert __NAME__(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test___NAME___of_nothing_is_empty():
    assert __NAME__([]) == []
""",
    ),
    Helper(
        name="is_palindrome",
        aliases=("palindrome",),
        summary="Whether text reads the same backwards, ignoring case and punctuation.",
        imports=(),
        source='''
def __NAME__(text: str) -> bool:
    """True when the letters and digits of `text` read the same in both directions."""
    letters = [ch.lower() for ch in text if ch.isalnum()]
    return letters == letters[::-1]
''',
        test_imports=(),
        tests="""
def test___NAME___ignores_case_and_punctuation():
    assert __NAME__("A man, a plan, a canal: Panama")


def test___NAME___rejects_other_text():
    assert not __NAME__("ledger")
""",
    ),
    Helper(
        name="format_money",
        aliases=("format_currency", "money_to_str", "format_amount"),
        summary="Format an amount with its currency code, thousands separators and cents.",
        imports=("from decimal import ROUND_HALF_UP, Decimal",),
        source='''
def __NAME__(amount: Decimal | float | int | str, currency: str = "USD") -> str:
    """`amount` as `USD 1,234.50`: two decimals, halves rounded up, thousands separated."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{currency} {value:,.2f}"
''',
        test_imports=("from decimal import Decimal",),
        tests="""
def test___NAME___adds_separators_and_cents():
    assert __NAME__(Decimal("1234.5")) == "USD 1,234.50"


def test___NAME___uses_the_currency_code():
    assert __NAME__("0.125", "EUR") == "EUR 0.13"
""",
    ),
)


def find(name: str) -> Helper | None:
    wanted = name.lower()
    for helper in HELPERS:
        if wanted == helper.name or wanted in helper.aliases:
            return helper
    return None


def names() -> list[str]:
    return [helper.name for helper in HELPERS]
