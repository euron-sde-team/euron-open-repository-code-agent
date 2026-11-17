from __future__ import annotations

from codeagent.agent.mutations import mutations

SOURCE = '''def apply_discount(subtotal, threshold, rate):
    if subtotal > threshold:
        return subtotal - subtotal * rate
    return subtotal


def volume(quantity):
    for minimum in range(10, 0, -1):
        if quantity >= minimum and quantity < 100:
            return minimum
    return 0
'''


def test_a_comparison_can_be_relaxed_to_include_the_boundary() -> None:
    found = mutations(SOURCE, 1, 4, set())
    descriptions = {m.apply(SOURCE).splitlines()[1].strip() for m in found}
    assert "if subtotal >= threshold:" in descriptions


def test_every_candidate_is_valid_python() -> None:
    import ast

    for mutation in mutations(SOURCE, 1, 11, {"10"}):
        ast.parse(mutation.apply(SOURCE))


def test_hints_from_the_failure_rank_matching_constants_first() -> None:
    plain = mutations(SOURCE, 7, 11, set())
    hinted = mutations(SOURCE, 7, 11, {"10"})
    assert hinted[0].priority >= plain[0].priority
    assert any(m.original == "10" for m in hinted[:3])


def test_boolean_operators_are_candidates() -> None:
    assert any(" or " in m.apply(SOURCE) for m in mutations(SOURCE, 9, 9, set()))


def test_mutations_stay_inside_the_requested_lines() -> None:
    assert all(m.line <= 4 for m in mutations(SOURCE, 1, 4, set()))


def test_candidates_are_unique() -> None:
    found = mutations(SOURCE, 1, 11, set())
    keys = [(m.line, m.start, m.replacement) for m in found]
    assert len(keys) == len(set(keys))
