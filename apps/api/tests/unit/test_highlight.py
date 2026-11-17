from __future__ import annotations

from codeagent.codeintel.highlight import highlight_lines

CLASSES = {"kw", "str", "com", "num", "fn", "cls", "op", "bi", "dec", "var", "punc", "plain", ""}


def test_every_line_of_the_source_is_returned_and_round_trips() -> None:
    source = "def add(a, b):\n    # sum\n    return a + b\n"
    lines = highlight_lines(source, "Python", "m.py")
    assert len(lines) == 3
    assert ["".join(text for _, text in line) for line in lines] == source.split("\n")[:3]


def test_tokens_use_the_stable_class_names() -> None:
    lines = highlight_lines('x = "hi"  # note\ndef f(): return 42\n', "Python", "m.py")
    flat = [css for line in lines for css, _ in line]
    assert set(flat) <= CLASSES
    assert {"kw", "str", "com", "num"} <= set(flat)


def test_unknown_languages_fall_back_to_plain_text() -> None:
    lines = highlight_lines("just words\n", "Text", "notes.xyz")
    assert lines[0] == [("plain", "just words")] or lines[0] == [("", "just words")]


def test_markup_in_code_stays_text() -> None:
    lines = highlight_lines("<script>alert(1)</script>\n", "Text", "a.txt")
    assert "".join(t for _, t in lines[0]) == "<script>alert(1)</script>"
