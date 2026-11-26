"""Общие предикаты версии шаблона (`core/pack_studio/outcome/predicates.py`): их читают и вычислитель результата, и
движок (план подписей, пакет сдачи, анкеты, настройки проекта, предпросмотр)."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant, VisibleIf
from hse_doc_studio.core.pack_studio.outcome.predicates import (
    chosen_variant_id,
    document_in_scope,
    field_visible_for_kind,
    item_off_reason,
    item_skipped,
    kind_allowed,
    kinds_restrict,
    manual_selected,
    nda_enabled,
    output_arcname,
    owner_short_name,
    resolve_output_names,
    staffing_allowed,
    variant_available,
    visible_if_held,
    with_owner_suffix,
)
from hse_doc_studio.core.value_objects import ChecksOverride


def _doc(
    doc_id: str = "d", *, variants: tuple[DocumentVariant, ...] = (), names: dict[str, str] | None = None
) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        name={"ru": doc_id},
        code={},
        source_file=None if variants else f"{doc_id}.tex",
        output_file=None if variants else f"{doc_id}.pdf",
        output_name=names if names is not None else {"ru": f"{doc_id}.pdf"},
        gost_ref=None,
        required=True,
        checks=ChecksOverride(),
        variants=variants,
    )


def _variant(variant_id: str, names: dict[str, str] | None = None, langs: tuple[str, ...] = ()) -> DocumentVariant:
    return DocumentVariant(
        id=variant_id,
        label={"ru": variant_id},
        source_file=f"{variant_id}.tex",
        output_file=f"{variant_id}.pdf",
        output_name=names or {},
        engine=None,
        supported_langs=langs,
    )


def test__kind_and_staffing_gates__membership() -> None:
    assert kind_allowed(("project",), "project")
    assert not kind_allowed(("project",), "research")
    assert staffing_allowed(("solo", "team"), "team")
    assert not staffing_allowed(("team",), "solo")


def test__document_in_scope__both_gates_must_hold() -> None:
    assert document_in_scope(("project",), ("solo",), "project", "solo")
    assert not document_in_scope(("project",), ("solo",), "research", "solo")
    assert not document_in_scope(("project",), ("solo",), "project", "team")


def test__field_visible_for_kind__empty_list_means_every_kind() -> None:
    assert field_visible_for_kind((), "research")
    assert field_visible_for_kind(("project",), "project")
    assert not field_visible_for_kind(("project",), "research")


@pytest.mark.parametrize(
    ("kinds", "restricts"),
    [((), False), (("research", "project"), False), (("project", "research"), False), (("project",), True)],
)
def test__kinds_restrict__only_a_proper_subset_restricts(kinds: tuple[str, ...], restricts: bool) -> None:
    assert kinds_restrict(kinds) is restricts


def test__nda_enabled__truthiness_of_meta() -> None:
    assert nda_enabled({"nda": True})
    assert not nda_enabled({"nda": False})
    assert not nda_enabled({})


@pytest.mark.parametrize(
    ("selection", "programmer", "operator"),
    [
        ("", True, True),
        ("Программиста и оператора", True, True),
        ("Только программиста", True, False),
        ("только оператора", False, True),
        ("что-то своё", True, True),
    ],
)
def test__manual_selected__marker_substrings_with_both_as_the_fallback(
    selection: str, programmer: bool, operator: bool
) -> None:
    assert manual_selected(selection, "programmer_manual") is programmer
    assert manual_selected(selection, "operator_manual") is operator


@pytest.mark.parametrize(
    ("skip_if_nda", "kinds", "kind", "nda", "doc_state", "expected"),
    [
        (False, ("research", "project"), "project", False, "active", None),
        (True, ("research", "project"), "project", True, "active", "nda"),
        (True, ("research", "project"), "project", False, "active", None),
        (False, ("research",), "project", False, "active", "kind"),
        (False, ("research", "project"), "project", False, "absent", "absent"),
        (False, ("research", "project"), "project", False, "inactive", "inactive"),
        # NDA главнее вида работы, вид работы главнее состояния документа.
        (True, ("research",), "project", True, "absent", "nda"),
        (False, ("research",), "project", False, "absent", "kind"),
    ],
)
def test__item_off_reason__priority_nda_kind_then_document(
    skip_if_nda: bool, kinds: tuple[str, ...], kind: str, nda: bool, doc_state: str, expected: str | None
) -> None:
    got = item_off_reason(skip_if_nda=skip_if_nda, item_kinds=kinds, kind=kind, nda=nda, doc_state=doc_state)

    assert got == expected


def test__item_skipped__ignores_the_state_of_the_document() -> None:
    assert item_skipped(skip_if_nda=True, item_kinds=("project",), kind="project", nda=True)
    assert item_skipped(skip_if_nda=False, item_kinds=("research",), kind="project", nda=False)
    assert not item_skipped(skip_if_nda=True, item_kinds=("project",), kind="project", nda=False)


def test__visible_if_held__compares_the_answer_with_equals() -> None:
    condition = VisibleIf(field="used_ai", equals="yes")

    assert visible_if_held(None, {})
    assert visible_if_held(condition, {"used_ai": "yes"})
    assert not visible_if_held(condition, {"used_ai": "no"})
    assert not visible_if_held(condition, {})
    assert visible_if_held(VisibleIf(field="agree", equals=True), {"agree": True})


def test__chosen_variant_id__only_the_presentation_honours_the_request() -> None:
    variants = (_variant("pptx"), _variant("beamer"))

    assert chosen_variant_id(_doc("presentation", variants=variants), "beamer") == "beamer"
    assert chosen_variant_id(_doc("presentation", variants=variants), "nope") == "pptx"
    assert chosen_variant_id(_doc("presentation", variants=variants), None) == "pptx"
    assert chosen_variant_id(_doc("spec", variants=variants), "beamer") == "pptx"
    assert chosen_variant_id(_doc("plain"), "beamer") is None


def test__variant_available__empty_languages_means_all() -> None:
    assert variant_available((), "ru")
    assert variant_available(("en",), "en")
    assert not variant_available(("en",), "ru")


def test__output_names__variant_names_win_and_language_falls_back_to_russian_then_file() -> None:
    plain = _doc("tz", names={"ru": "ТЗ.pdf", "en": "SoW.pdf"})
    varied = _doc(
        "pres", variants=(_variant("a", {"ru": "A.pdf"}), _variant("b", {"ru": "B.pdf"})), names={"ru": "x.pdf"}
    )

    assert resolve_output_names(plain, None) == {"ru": "ТЗ.pdf", "en": "SoW.pdf"}
    assert resolve_output_names(varied, "b") == {"ru": "B.pdf"}
    assert resolve_output_names(varied, "missing") == {"ru": "A.pdf"}
    assert output_arcname({"ru": "ТЗ.pdf", "en": "SoW.pdf"}, "en", "f.pdf") == "SoW.pdf"
    assert output_arcname({"ru": "ТЗ.pdf"}, "en", "f.pdf") == "ТЗ.pdf"
    assert output_arcname({}, "en", "f.pdf") == "f.pdf"


def test__owner_suffix__surname_goes_before_the_extension() -> None:
    assert owner_short_name("Иванов Иван Иванович", "ivanov") == "Иванов"
    assert owner_short_name("", "ivanov") == "ivanov"
    assert owner_short_name("", None) == ""
    assert with_owner_suffix("ТЗ.pdf", "Иванов") == "ТЗ — Иванов.pdf"
    assert with_owner_suffix("ТЗ", "Иванов") == "ТЗ — Иванов"
    assert with_owner_suffix("ТЗ.pdf", None) == "ТЗ.pdf"
    assert with_owner_suffix("ТЗ.pdf", "") == "ТЗ.pdf"


@pytest.mark.parametrize(
    ("full_name", "lang", "surname"),
    [
        # Русский проект: фамилия первое слово, как было.
        ("Иванов Иван Иванович", "ru", "Иванов"),
        ("Иванов И. И.", "ru", "Иванов"),
        ("Ivan Ivanov", "ru", "Ivan"),
        # Английский проект: «Given Surname», инициалы не фамилия.
        ("Ivan Ivanov", "en", "Ivanov"),
        ("Maria S. Petrova", "en", "Petrova"),
        ("I. I. Ivanov", "en", "Ivanov"),
        ("Ivanov I.I.", "en", "Ivanov"),
        ("Ivanov, Ivan", "en", "Ivanov"),
        ("Ivanov", "en", "Ivanov"),
        ("I. I.", "en", "I."),
        # ФИО кириллицей в английском проекте записано по-русски.
        ("Иванов Иван Иванович", "en", "Иванов"),
    ],
)
def test__owner_short_name__surname_by_project_language(full_name: str, lang: str, surname: str) -> None:
    assert owner_short_name(full_name, "slug", lang) == surname


def test__owner_short_name__no_name__falls_back_to_the_slug_in_any_language() -> None:
    assert owner_short_name("", "ivanov", "en") == "ivanov"
    assert owner_short_name("  ", None, "en") == ""
