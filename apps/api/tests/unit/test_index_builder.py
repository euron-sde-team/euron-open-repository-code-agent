"""The index builder against the bundled sample repositories."""

from __future__ import annotations

from codeagent.codeintel.builder import IndexBuild, build_index


def test_ledgerkit_is_indexed_completely(ledgerkit: IndexBuild) -> None:
    stats = ledgerkit.stats()
    assert stats["files"] == stats["indexed_files"] == 15
    assert stats["test_files"] == 6
    assert stats["symbols"] > 50
    assert stats["chunks"] >= stats["indexed_files"]
    assert ledgerkit.warnings == []
    assert "Python" in ledgerkit.languages()


def test_python_symbols_have_qualified_names_and_kinds(ledgerkit: IndexBuild) -> None:
    by_name = {s.qualified_name: s for s in ledgerkit.symbols}
    assert by_name["ledgerkit.pricing.apply_discount"].kind == "function"
    assert by_name["ledgerkit.invoice.Invoice"].kind == "class"
    assert by_name["ledgerkit.invoice.Invoice.add_line"].kind == "method"
    assert by_name["ledgerkit.export.CSV_HEADER"].kind == "constant"
    discount = by_name["ledgerkit.pricing.apply_discount"]
    assert discount.signature.startswith("def apply_discount(")
    assert "threshold" in discount.doc


def test_methods_point_at_their_class(ledgerkit: IndexBuild) -> None:
    by_name = {s.qualified_name: s for s in ledgerkit.symbols}
    klass = by_name["ledgerkit.invoice.Invoice"]
    method = by_name["ledgerkit.invoice.Invoice.add_line"]
    assert method.parent_id == klass.id
    assert method.depth == klass.depth + 1


def test_calls_and_imports_resolve_into_a_graph(ledgerkit: IndexBuild) -> None:
    target = next(
        s for s in ledgerkit.symbols if s.qualified_name == "ledgerkit.pricing.apply_discount"
    )
    incoming = [r for r in ledgerkit.refs if r.target_symbol_id == target.id]
    assert {"call", "import"} <= {r.kind for r in incoming}
    assert target.ref_count == len(incoming)
    # Used by the invoice module and tested in test_pricing.
    files = {f.id: f.path for f in ledgerkit.files}
    assert any(files[r.file_id] == "ledgerkit/invoice.py" for r in incoming)
    assert any(files[r.file_id] == "tests/test_pricing.py" for r in incoming)


def test_most_references_resolve(ledgerkit: IndexBuild) -> None:
    stats = ledgerkit.stats()
    assert stats["resolved_references"] / stats["references"] > 0.4


def test_go_is_extracted_with_tree_sitter(ratelimit: IndexBuild) -> None:
    names = {(s.qualified_name, s.kind) for s in ratelimit.symbols}
    assert ("Limiter", "struct") in names
    assert ("Limiter.Allow", "method") in names
    assert ("New", "function") in names
    assert ("store.Memory.Get", "method") in names


def test_typescript_and_tsx_are_extracted(checkout_web: IndexBuild) -> None:
    names = {(s.qualified_name, s.kind) for s in checkout_web.symbols}
    assert ("cart.Cart", "class") in names
    assert ("cart.Cart.addItem", "method") in names
    assert ("api.client.Product", "interface") in names
    languages = checkout_web.languages()
    assert "TypeScript" in languages
    assert "TSX" in languages


def test_chunks_cover_symbols_and_carry_their_location(ledgerkit: IndexBuild) -> None:
    files = {f.id: f for f in ledgerkit.files}
    chunk = next(
        c for c in ledgerkit.chunks if "apply_discount" in c.content and "def " in c.content
    )
    assert chunk.embed_text.startswith(files[chunk.file_id].path)
    assert 1 <= chunk.start_line <= chunk.end_line <= files[chunk.file_id].line_count
    assert chunk.terms


def test_binary_oversized_and_broken_files_do_not_fail_the_build() -> None:
    build = build_index(
        [
            ("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00", 11),
            ("big.py", b"x = 1\n" * 10, 5_000_000),
            ("broken.py", b"def oops(:\n    pass\n", 20),
            ("ok.py", b"def fine():\n    return 1\n", 24),
        ],
        max_file_bytes=1_000_000,
        chunk_max_lines=60,
    )
    by_path = {f.path: f for f in build.files}
    assert by_path["logo.png"].content is None
    assert by_path["big.py"].content is None
    assert by_path["broken.py"].parse_error
    assert {w["path"] for w in build.warnings} >= {"big.py", "broken.py"}
    assert any(s.name == "fine" for s in build.symbols)


def test_long_functions_are_split_into_overlapping_chunks() -> None:
    body = "\n".join(f"    total += {i}" for i in range(150))
    source = f"def long_one():\n    total = 0\n{body}\n    return total\n".encode()
    build = build_index(
        [("long.py", source, len(source))], max_file_bytes=10**6, chunk_max_lines=40
    )
    spans = sorted((c.start_line, c.end_line) for c in build.chunks)
    assert len(spans) >= 4
    assert all(end - start < 45 for start, end in spans)
    assert any(spans[i + 1][0] <= spans[i][1] for i in range(len(spans) - 1))
