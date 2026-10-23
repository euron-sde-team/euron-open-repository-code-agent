"""JavaScript, TypeScript, TSX and Go symbols from tree-sitter syntax trees.

The walkers read the concrete syntax tree node by node (no query files), which keeps the
grammar-version surface small: they rely only on node types and field names that have been
stable across tree-sitter releases. Parsers are created once per language and reused.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import cache

import tree_sitter_go
import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from codeagent.codeintel import languages
from codeagent.codeintel.symbols.types import (
    FileOutline,
    ImportDraft,
    RefDraft,
    RefKind,
    SymbolDraft,
    SymbolKind,
    first_paragraph,
    one_line,
)

_CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]*$")
_EXTENDS = re.compile(r"extends\s+([A-Za-z_$][\w$.]*)")
_FUNCTION_VALUES = frozenset(
    {"arrow_function", "function_expression", "function", "generator_function"}
)


@cache
def _parser(language: str) -> Parser:
    if language == languages.JAVASCRIPT:
        grammar = tree_sitter_javascript.language()
    elif language == languages.TYPESCRIPT:
        grammar = tree_sitter_typescript.language_typescript()
    elif language == languages.TSX:
        grammar = tree_sitter_typescript.language_tsx()
    elif language == languages.GO:
        grammar = tree_sitter_go.language()
    else:
        raise ValueError(f"no tree-sitter grammar for {language}")
    return Parser(Language(grammar))


def _text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", "replace")


def _line(node: Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: Node) -> int:
    return node.end_point[0] + 1


def _head(node: Node, body_field: str = "body") -> str:
    """The declaration text before its body: the signature as written."""
    body = node.child_by_field_name(body_field)
    text = _text(node)
    if body is not None:
        text = text[: body.start_byte - node.start_byte]
    return one_line(text.rstrip(" {=>\n"), 240)


def _comment_text(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        line = re.sub(r"^(/\*\*?|\*/|\*|//+)", "", line).strip()
        line = line.removesuffix("*/").strip()
        lines.append(line)
    return "\n".join(lines)


def _leading_doc(node: Node) -> str:
    """The comment block directly above a declaration (JSDoc, // lines, Go doc comments)."""
    comments: list[str] = []
    expected = node.start_point[0] - 1
    sibling = node.prev_named_sibling
    while sibling is not None and sibling.type == "comment" and sibling.end_point[0] == expected:
        comments.append(_text(sibling))
        expected = sibling.start_point[0] - 1
        sibling = sibling.prev_named_sibling
    return first_paragraph(_comment_text("\n".join(reversed(comments))))


def _descendants(node: Node, stop: frozenset[str]) -> Iterator[Node]:
    stack = list(reversed(node.named_children))
    while stack:
        current = stack.pop()
        yield current
        if current.type in stop:
            continue
        stack.extend(reversed(current.named_children))


class _Walker:
    def __init__(self, language: str, module: str) -> None:
        self.language = language
        self.module = module
        self.outline = FileOutline()

    def qualified(self, *names: str) -> str:
        return ".".join(part for part in (self.module, *names) if part)

    def add(
        self,
        node: Node,
        name: str,
        kind: SymbolKind,
        *,
        path: tuple[str, ...] = (),
        parent: int | None = None,
        exported: bool,
        signature: str,
        doc_anchor: Node | None = None,
    ) -> int:
        key = len(self.outline.symbols)
        self.outline.symbols.append(
            SymbolDraft(
                key=key,
                name=name,
                qualified_name=self.qualified(*path, name),
                kind=kind,
                start_line=_line(doc_anchor if doc_anchor is not None else node),
                end_line=_end_line(node),
                signature=signature,
                doc=_leading_doc(doc_anchor or node),
                parent=parent,
                exported=exported,
            )
        )
        return key


class _ScriptWalker(_Walker):
    """JavaScript, TypeScript and TSX."""

    _NESTED = frozenset({"function_declaration", "class_declaration", "method_definition"})

    def run(self, root: Node) -> FileOutline:
        for child in root.named_children:
            self.statement(child, exported=False, anchor=None)
        return self.outline

    def statement(self, node: Node, *, exported: bool, anchor: Node | None) -> None:
        kind = node.type
        if kind == "export_statement":
            declaration = node.child_by_field_name("declaration")
            if declaration is not None:
                self.statement(declaration, exported=True, anchor=node)
            else:
                self.calls(node, None)
        elif kind in {"function_declaration", "generator_function_declaration"}:
            self.function(node, exported=exported, anchor=anchor)
        elif kind in {"class_declaration", "abstract_class_declaration"}:
            self.class_declaration(node, exported=exported, anchor=anchor)
        elif kind in {"lexical_declaration", "variable_declaration"}:
            self.variables(node, exported=exported, anchor=anchor)
        elif kind in {"interface_declaration", "type_alias_declaration", "enum_declaration"}:
            name = _text(node.child_by_field_name("name"))
            if name:
                symbol_kind = {
                    "interface_declaration": SymbolKind.INTERFACE,
                    "type_alias_declaration": SymbolKind.TYPE,
                    "enum_declaration": SymbolKind.ENUM,
                }[kind]
                self.add(
                    node,
                    name,
                    symbol_kind,
                    exported=exported,
                    signature=one_line(_text(node).split("{", 1)[0], 200),
                    doc_anchor=anchor or node,
                )
        elif kind == "import_statement":
            self.import_statement(node)
        else:
            self.calls(node, None)

    def function(self, node: Node, *, exported: bool, anchor: Node | None) -> None:
        name = _text(node.child_by_field_name("name"))
        if not name:
            return
        key = self.add(
            node, name, SymbolKind.FUNCTION, exported=exported, signature=_head(node),
            doc_anchor=anchor or node,
        )  # fmt: skip
        body = node.child_by_field_name("body")
        if body is not None:
            self.calls(body, key)

    def class_declaration(self, node: Node, *, exported: bool, anchor: Node | None) -> None:
        name = _text(node.child_by_field_name("name"))
        if not name:
            return
        key = self.add(
            node, name, SymbolKind.CLASS, exported=exported, signature=_head(node),
            doc_anchor=anchor or node,
        )  # fmt: skip
        for heritage in (c for c in node.named_children if c.type == "class_heritage"):
            match = _EXTENDS.search(_text(heritage))
            if match:
                qualifier, _, target = match.group(1).rpartition(".")
                self.outline.refs.append(
                    RefDraft(target, RefKind.INHERIT, _line(heritage), key, qualifier or None)
                )
        body = node.child_by_field_name("body")
        if body is None:
            return
        for member in body.named_children:
            if member.type == "method_definition":
                method = _text(member.child_by_field_name("name"))
                if not method:
                    continue
                method_key = self.add(
                    member, method, SymbolKind.METHOD, path=(name,), parent=key,
                    exported=exported and not method.startswith("#"), signature=_head(member),
                )  # fmt: skip
                method_body = member.child_by_field_name("body")
                if method_body is not None:
                    self.calls(method_body, method_key)
            else:
                self.calls(member, key)

    def variables(self, node: Node, *, exported: bool, anchor: Node | None) -> None:
        for declarator in (c for c in node.named_children if c.type == "variable_declarator"):
            name_node = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")
            name = (
                _text(name_node) if name_node is not None and name_node.type == "identifier" else ""
            )
            if name and value is not None and value.type in _FUNCTION_VALUES:
                text = _text(declarator)
                arrow = text.find("=>")
                signature = text[: arrow + 2] if arrow > 0 else text.split("{", 1)[0]
                prefix = _text(node).split(" ", 1)[0]
                key = self.add(
                    node, name, SymbolKind.FUNCTION, exported=exported,
                    signature=one_line(f"{prefix} {signature}", 240), doc_anchor=anchor or node,
                )  # fmt: skip
                body = value.child_by_field_name("body")
                self.calls(body if body is not None else value, key)
            elif name and _CONSTANT.match(name) and value is not None:
                self.add(
                    node, name, SymbolKind.CONSTANT, exported=exported,
                    signature=one_line(_text(declarator), 160), doc_anchor=anchor or node,
                )  # fmt: skip
                self.calls(value, None)
            elif value is not None:
                self.calls(value, None)

    def import_statement(self, node: Node) -> None:
        module = _text(node.child_by_field_name("source")).strip("'\"`")
        line = _line(node)
        for clause in (c for c in node.named_children if c.type == "import_clause"):
            for part in clause.named_children:
                if part.type == "identifier":
                    self.imported(_text(part), module, "default", line)
                elif part.type == "named_imports":
                    for spec in (s for s in part.named_children if s.type == "import_specifier"):
                        name = _text(spec.child_by_field_name("name"))
                        alias = _text(spec.child_by_field_name("alias")) or name
                        if name:
                            self.imported(alias, module, name, line)
                elif part.type == "namespace_import":
                    alias = next(
                        (_text(c) for c in part.named_children if c.type == "identifier"), ""
                    )
                    if alias:
                        self.imported(alias, module, None, line)

    def imported(self, alias: str, module: str, name: str | None, line: int) -> None:
        self.outline.imports.append(ImportDraft(alias, module, name, line))
        target = name if name and name != "default" else alias
        self.outline.refs.append(RefDraft(target, RefKind.IMPORT, line, None, module or None))

    def calls(self, node: Node, source: int | None) -> None:
        for child in _descendants(node, self._NESTED):
            if child.type == "call_expression":
                function = child.child_by_field_name("function")
                self.callee(function, child, source)
            elif child.type == "new_expression":
                constructor = child.child_by_field_name("constructor")
                self.callee(constructor, child, source)

    def callee(self, function: Node | None, call: Node, source: int | None) -> None:
        if function is None:
            return
        if function.type == "identifier":
            self.outline.refs.append(RefDraft(_text(function), RefKind.CALL, _line(call), source))
        elif function.type == "member_expression":
            target = _text(function.child_by_field_name("property"))
            qualifier = _text(function.child_by_field_name("object"))
            if target:
                self.outline.refs.append(
                    RefDraft(
                        target, RefKind.CALL, _line(call), source, one_line(qualifier, 80) or None
                    )
                )


class _GoWalker(_Walker):
    def run(self, root: Node) -> FileOutline:
        receivers: list[tuple[int, str]] = []
        for child in root.named_children:
            kind = child.type
            if kind == "function_declaration":
                self.function(child)
            elif kind == "method_declaration":
                linked = self.method(child)
                if linked:
                    receivers.append(linked)
            elif kind == "type_declaration":
                self.types(child)
            elif kind == "const_declaration":
                self.constants(child)
            elif kind == "import_declaration":
                self.imports(child)
            else:
                self.calls(child, None)
        # Methods may come before their type in the file: link parents in a second pass.
        types = {
            s.name: s.key
            for s in self.outline.symbols
            if s.kind in {SymbolKind.STRUCT, SymbolKind.TYPE, SymbolKind.INTERFACE}
        }
        for key, receiver_type in receivers:
            if receiver_type in types:
                self.outline.symbols[key].parent = types[receiver_type]
        return self.outline

    def function(self, node: Node) -> None:
        name = _text(node.child_by_field_name("name"))
        if not name:
            return
        key = self.add(
            node, name, SymbolKind.FUNCTION, exported=name[:1].isupper(), signature=_head(node)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            self.calls(body, key)

    def method(self, node: Node) -> tuple[int, str] | None:
        name = _text(node.child_by_field_name("name"))
        if not name:
            return None
        receiver = ""
        parameters = node.child_by_field_name("receiver")
        if parameters is not None:
            for declaration in parameters.named_children:
                type_node = declaration.child_by_field_name("type")
                receiver = _text(type_node).lstrip("*").split("[", 1)[0]
        key = self.add(
            node, name, SymbolKind.METHOD, path=(receiver,) if receiver else (),
            exported=name[:1].isupper(), signature=_head(node),
        )  # fmt: skip
        body = node.child_by_field_name("body")
        if body is not None:
            self.calls(body, key)
        return (key, receiver) if receiver else None

    def types(self, node: Node) -> None:
        for spec in (c for c in node.named_children if c.type in {"type_spec", "type_alias"}):
            name = _text(spec.child_by_field_name("name"))
            type_node = spec.child_by_field_name("type")
            if not name:
                continue
            kind = SymbolKind.TYPE
            if type_node is not None and type_node.type == "struct_type":
                kind = SymbolKind.STRUCT
            elif type_node is not None and type_node.type == "interface_type":
                kind = SymbolKind.INTERFACE
            self.add(
                spec, name, kind, exported=name[:1].isupper(),
                signature=one_line(f"type {_text(spec).split('{', 1)[0]}", 200),
                doc_anchor=node if len(node.named_children) == 1 else spec,
            )  # fmt: skip

    def constants(self, node: Node) -> None:
        for spec in (c for c in node.named_children if c.type == "const_spec"):
            for name_node in spec.children_by_field_name("name"):
                name = _text(name_node)
                if name and name != "_":
                    self.add(
                        spec, name, SymbolKind.CONSTANT, exported=name[:1].isupper(),
                        signature=one_line(f"const {_text(spec)}", 160),
                    )  # fmt: skip

    def imports(self, node: Node) -> None:
        specs = [c for c in _descendants(node, frozenset()) if c.type == "import_spec"]
        for spec in specs:
            path = _text(spec.child_by_field_name("path")).strip('"`')
            alias = _text(spec.child_by_field_name("name")) or path.rsplit("/", 1)[-1]
            line = _line(spec)
            self.outline.imports.append(ImportDraft(alias, path, None, line))
            self.outline.refs.append(
                RefDraft(path.rsplit("/", 1)[-1], RefKind.IMPORT, line, None, path)
            )

    def calls(self, node: Node, source: int | None) -> None:
        for child in _descendants(node, frozenset({"function_declaration", "method_declaration"})):
            if child.type != "call_expression":
                continue
            function = child.child_by_field_name("function")
            if function is None:
                continue
            if function.type == "identifier":
                self.outline.refs.append(
                    RefDraft(_text(function), RefKind.CALL, _line(child), source)
                )
            elif function.type == "selector_expression":
                target = _text(function.child_by_field_name("field"))
                qualifier = _text(function.child_by_field_name("operand"))
                if target:
                    self.outline.refs.append(
                        RefDraft(
                            target,
                            RefKind.CALL,
                            _line(child),
                            source,
                            one_line(qualifier, 80) or None,
                        )
                    )


def extract_treesitter(language: str, source: str, *, module: str = "") -> FileOutline:
    tree = _parser(language).parse(source.encode("utf-8"))
    walker: _ScriptWalker | _GoWalker = (
        _GoWalker(language, module) if language == languages.GO else _ScriptWalker(language, module)
    )
    outline = walker.run(tree.root_node)
    if tree.root_node.has_error and not outline.symbols:
        outline.error = f"{language} syntax error: the file could not be parsed"
    return outline


def script_module(path: str) -> str:
    """`src/cart/pricing.ts` -> `cart.pricing`; `index.ts` files take their folder's name."""
    stem = re.sub(r"\.(d\.)?(m|c)?(js|jsx|ts|tsx)$", "", path)
    parts = stem.split("/")
    if parts and parts[0] in {"src", "lib", "app"}:
        parts = parts[1:]
    if len(parts) > 1 and parts[-1] == "index":
        parts = parts[:-1]
    return ".".join(parts)
