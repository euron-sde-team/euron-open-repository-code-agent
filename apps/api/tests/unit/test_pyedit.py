from __future__ import annotations

import ast

from codeagent.agent import pyedit


def test_defines_finds_functions_classes_and_constants() -> None:
    source = "X = 1\n\ndef f(): ...\n\nclass C:\n    def m(self): ...\n"
    assert pyedit.defines(source, "f")
    assert pyedit.defines(source, "C")
    assert pyedit.defines(source, "X")
    assert not pyedit.defines(source, "g")


def test_imports_are_added_once_after_the_docstring_and_future_imports() -> None:
    source = '"""Doc."""\n\nfrom __future__ import annotations\n\nimport os\n\nx = os.sep\n'
    out = pyedit.insert_imports(source, ["from decimal import Decimal", "import os"])
    assert out.count("import os") == 1
    assert "from decimal import Decimal" in out
    ast.parse(out)
    assert out.index("__future__") < out.index("decimal")


def test_a_definition_is_appended_with_blank_lines() -> None:
    out = pyedit.append_definition("x = 1\n", "def f():\n    return 1\n")
    assert out.endswith("def f():\n    return 1\n")
    assert "\n\n\ndef f" in out
    ast.parse(out)


def test_all_is_extended_when_it_exists_and_left_alone_when_it_does_not() -> None:
    assert '"clamp"' in pyedit.add_to_all('__all__ = ["a"]\n', "clamp")
    assert pyedit.add_to_all("x = 1\n", "clamp") == "x = 1\n"
