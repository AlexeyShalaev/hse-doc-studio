"""Трасса решений, ревизия и перевод результата в словарь контракта."""

from __future__ import annotations

from hse_doc_studio.core.pack_studio.outcome.model import ElementRef, RuleRef, Term, VariantOption
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.revision import REVISION_PREFIX, revision_of
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer, builtin_rule, manifest_rule, why

_RULE = manifest_rule("files/a/doc.yaml", "/supported_kinds")


def _decide(tracer: Tracer, element: str, *, status: str = "held") -> str:
    return tracer.decide(
        rule=_RULE,
        kind="supported_kinds",
        effect="gate",
        terms=[Term("in", "kind", ("project",))],
        actual={"kind": "project"},
        status=status,  # type: ignore[arg-type]
        subjects=[ElementRef("documents", element)],
    )


def test__tracer__equal_decisions_are_merged_and_collect_subjects() -> None:
    tracer = Tracer()

    first = _decide(tracer, "a")
    second = _decide(tracer, "b")
    other = _decide(tracer, "a", status="not_held")

    assert first == second == "t1"
    assert other == "t2"
    entries = tracer.entries()
    assert [e.id for e in entries] == ["t1", "t2"]
    assert [s.id for s in entries[0].subjects] == ["a", "b"]
    assert tracer.status_of("t2") == "not_held"
    assert tracer.status_of("t9") is None


def test__tracer__subject_is_not_repeated() -> None:
    tracer = Tracer()

    _decide(tracer, "a")
    _decide(tracer, "a")

    assert len(tracer.entries()[0].subjects) == 1


def test__tracer__disabled__keeps_nothing_and_returns_empty_ids() -> None:
    tracer = Tracer(enabled=False)

    assert _decide(tracer, "a") == ""
    assert tracer.entries() == ()
    assert why("", "") == ()


def test__why__drops_empty_ids_and_repeats_in_order() -> None:
    assert why("t2", "", "t1", "t2") == ("t2", "t1")


def test__rules__builtin_and_manifest_references() -> None:
    assert builtin_rule("nda_gate") == RuleRef(origin="builtin", builtin="nda_gate")
    assert _RULE.file == "files/a/doc.yaml"
    assert _RULE.pointer == "/supported_kinds"


def test__revision__depends_on_texts_not_on_order() -> None:
    one = revision_of({"version.yaml": "a", "files/x/doc.yaml": "b"})
    swapped = revision_of({"files/x/doc.yaml": "b", "version.yaml": "a"})
    edited = revision_of({"version.yaml": "a!", "files/x/doc.yaml": "b"})

    assert one == swapped
    assert one != edited
    assert one.startswith(REVISION_PREFIX)
    assert revision_of({"version.yaml": b"a"}) == revision_of({"version.yaml": "a"})


def test__to_json__dataclasses_tuples_and_dicts_become_plain_json() -> None:
    option = VariantOption(id="a", label={"ru": "А"}, langs=("en",), available=False, chosen=False, why=("t1",))

    assert to_json(option) == {
        "id": "a",
        "label": {"ru": "А"},
        "langs": ["en"],
        "available": False,
        "chosen": False,
        "why": ["t1"],
    }
