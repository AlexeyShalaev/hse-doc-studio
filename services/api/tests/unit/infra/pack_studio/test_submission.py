"""Профили сдачи и порядок маршрута формой (template-studio.md, 5.5-5.8, срез T13): модель и точечные правки."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.core.pack_studio.submission import (
    ProfileHead,
    SubmissionEditError,
    SubmissionList,
    SubmissionOp,
    SubmissionOpKind,
)
from hse_doc_studio.infra.pack_studio.submission import PackSubmissionEditor
from hse_doc_studio.infra.template.yaml_template_repository import _parse_submission_profile

_REPO = Path(__file__).resolve().parents[6]
_EDITOR = PackSubmissionEditor()

_TEXT = """\
id: "2026.1.1"
documents: [proposal, report]
supported_kinds: [project, research]
nda: { form: nda }
forms:
  - id: code_link
    title: { ru: Ссылка, en: Link }
    required_for_pack: true
    output: { output_name: "Ссылка.txt", format: markdown }

signatures:
  slots:
    - id: author
      label: { ru: Автор, en: Author }
      applies_to: [proposal, report]
    - id: supervisor
      label: { ru: Руководитель, en: Supervisor }
      applies_to: [proposal, report]
      required: true
    - id: academic_supervisor
      label: { ru: Академрук, en: Academic supervisor }
      applies_to: [proposal]

# ── точки сдачи ──
pack_submission:
  profiles:
    - id: topic
      name:        { ru: "Заявка", en: "Application" }
      description: { ru: "Заявка на тему", en: "Topic application" }
      items:
        # Заявку подписывает руководитель.
        - doc_id: proposal
          signatures: [author, supervisor]
          methods: { supervisor: [image, detached] }
          review_hint: keep   # ключ от более новой Студии
      signing_route: [[author], [supervisor], [academic_supervisor]]
      signing_slots:
        - { doc_id: proposal, slot_id: academic_supervisor, when: { person: supervisor, role: company } }
      deadline_hint:
        ru: "Обычно в ноябре"
        en: "Usually in November"

    - id: final
      name:        { ru: "Защита", en: "Defence" }
      items:
        - doc_id: report
          signatures: [author]
"""


def _op(kind: SubmissionOpKind, **fields: Any) -> SubmissionOp:
    return SubmissionOp(op=kind, **fields)


def _profiles(text: str) -> list[dict[str, Any]]:
    return yaml.safe_load(text)["pack_submission"]["profiles"]


def test__describe__profiles_lists_slots_forms_and_route() -> None:
    model = _EDITOR.describe(_TEXT)

    assert model.documents == ("proposal", "report")
    assert model.has_nda is True
    assert [s.id for s in model.slots] == ["author", "supervisor", "academic_supervisor"]
    assert model.slots[1].required is True
    assert model.forms[0].source == ".hse-studio/forms/code_link.json"
    assert model.forms[0].output_name == "Ссылка.txt"
    assert model.route is None
    topic, final = model.profiles
    assert topic.error is None
    assert topic.items[0].entry is not None
    assert topic.items[0].entry.methods == (("supervisor", ("image", "detached")),)
    assert topic.signing_route == (("author",), ("supervisor",), ("academic_supervisor",))
    slot = topic.signing_slots[0].entry
    assert slot is not None
    assert slot.when is not None
    assert (slot.when.person, slot.when.role) == ("supervisor", "company")
    assert topic.deadline_hint == {"ru": "Обычно в ноябре", "en": "Usually in November"}
    assert final.signing_route is None
    assert final.deadline_hint is None


def test__describe__broken_entry_keeps_the_others_and_their_indexes() -> None:
    text = _TEXT.replace(
        "        - { doc_id: proposal, slot_id: academic_supervisor",
        "        - { doc_id: proposal }\n        - { doc_id: proposal, slot_id: academic_supervisor",
    )

    topic = _EDITOR.describe(text).profiles[0]

    assert topic.signing_slots[0].entry is None
    assert topic.signing_slots[0].error is not None
    assert topic.signing_slots[1].index == 1
    assert topic.signing_slots[1].entry is not None
    assert topic.error is not None


@pytest.mark.parametrize(
    "path",
    sorted((_REPO / "packs").glob("*/templates/*/versions/*/version.yaml")),
    ids=lambda p: "/".join(p.parts[-6:-1]),
)
def test__describe__every_pack_of_the_repository_reads_without_problems(path: Path) -> None:
    model = _EDITOR.describe(path.read_text(encoding="utf-8"))

    assert [p.error for p in model.profiles if p.error] == []
    assert all(e.entry is not None for p in model.profiles for e in (*p.items, *p.extra_items, *p.signing_slots))


@pytest.mark.parametrize(
    "path",
    sorted((_REPO / "packs").glob("*/templates/*/versions/*/version.yaml")),
    ids=lambda p: "/".join(p.parts[-6:-1]),
)
def test__set_entry__same_value_changes_nothing_byte_for_byte(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for profile in _EDITOR.describe(text).profiles:
        for item in profile.items:
            assert item.entry is not None
            value = {
                "doc_id": item.entry.doc_id,
                "signatures": list(item.entry.signatures),
                "methods": {slot: list(methods) for slot, methods in item.entry.methods},
                "skip_if_nda": item.entry.skip_if_nda,
                "supported_kinds": list(item.entry.supported_kinds),
            }
            op = _op(
                SubmissionOpKind.set_entry,
                profile=profile.index,
                entries=SubmissionList.items,
                index=item.index,
                value=value,
            )
            assert _EDITOR.apply(text, [op]) == text


def test__set_entry__methods_change_keeps_comment_and_unknown_key() -> None:
    op = _op(
        SubmissionOpKind.set_entry,
        profile=0,
        entries=SubmissionList.items,
        index=0,
        value={"doc_id": "proposal", "signatures": ["author", "supervisor"], "methods": {"supervisor": ["image"]}},
    )

    text = _EDITOR.apply(_TEXT, [op])

    assert "        # Заявку подписывает руководитель.\n" in text
    assert "          methods: { supervisor: [image] }\n" in text
    assert "          review_hint: keep   # ключ от более новой Студии\n" in text
    assert text.replace("[image]", "[image, detached]") == _TEXT


def test__set_entry__defaults_are_not_written() -> None:
    op = _op(
        SubmissionOpKind.add_entry,
        profile=1,
        entries=SubmissionList.items,
        value={
            "doc_id": "proposal",
            "signatures": ["supervisor"],
            "methods": {"supervisor": [], "author": ["image"]},
            "skip_if_nda": False,
            "supported_kinds": ["research", "project"],
        },
    )

    text = _EDITOR.apply(_TEXT, [op])

    assert _profiles(text)[1]["items"][1] == {"doc_id": "proposal", "signatures": ["supervisor"]}
    assert "        - doc_id: proposal\n          signatures: [supervisor]\n" in text


def test__add_entry__new_list_in_block_with_short_values_inline() -> None:
    op = _op(
        SubmissionOpKind.add_entry,
        profile=1,
        entries=SubmissionList.extra_items,
        value={"source": ".hse-studio/forms/code_link.json", "output_name": "a.txt", "supported_kinds": ["project"]},
    )

    text = _EDITOR.apply(_TEXT, [op])

    assert (
        "      extra_items:\n"
        "        - source: .hse-studio/forms/code_link.json\n"
        "          output_name: a.txt\n"
        "          supported_kinds: [project]\n"
    ) in text


def test__add_entry__signing_slot_next_to_one_line_entries_is_one_line() -> None:
    op = _op(
        SubmissionOpKind.add_entry,
        profile=0,
        entries=SubmissionList.signing_slots,
        value={"doc_id": "proposal", "slot_id": "supervisor", "when": None, "optional": True},
    )

    text = _EDITOR.apply(_TEXT, [op])

    assert "        - { doc_id: proposal, slot_id: supervisor, optional: true }\n" in text


def test__remove_entry__last_signing_slot_takes_the_key_away() -> None:
    op = _op(SubmissionOpKind.remove_entry, profile=0, entries=SubmissionList.signing_slots, index=0)

    text = _EDITOR.apply(_TEXT, [op])

    assert "signing_slots" not in text
    assert "deadline_hint" in text


def test__set_profile__head_and_hint_written_in_place() -> None:
    head = ProfileHead("final", {"ru": "Защита КП", "en": "Defence"}, {}, {"ru": "Обычно в июне", "en": "In June"})

    text = _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.set_profile, profile=1, head=head)])

    final = _profiles(text)[1]
    assert final["name"] == {"ru": "Защита КП", "en": "Defence"}
    assert "description" not in final
    assert final["deadline_hint"] == {"ru": "Обычно в июне", "en": "In June"}
    assert '      name:        { ru: "Защита КП", en: "Defence" }\n' in text


def test__set_profile__hint_with_a_date_is_refused_and_file_unchanged() -> None:
    head = ProfileHead("final", {"ru": "Защита", "en": "Defence"}, {}, {"ru": "До 20 июня 2027", "en": "By 20 June"})

    with pytest.raises(SubmissionEditError, match="concrete date"):
        _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.set_profile, profile=1, head=head)])


def test__set_profile__id_of_another_profile_is_refused() -> None:
    head = ProfileHead("topic", {"ru": "Защита", "en": "Defence"}, {})

    with pytest.raises(SubmissionEditError, match="already exists"):
        _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.set_profile, profile=1, head=head)])


def test__set_profile_route__written_after_items_and_removed_with_none() -> None:
    op = _op(SubmissionOpKind.set_profile_route, profile=1, steps=(("author",), ("supervisor", "academic_supervisor")))

    text = _EDITOR.apply(_TEXT, [op])

    assert "          signatures: [author]\n      signing_route: [[author], [supervisor, academic_supervisor]]\n" in text
    back = _EDITOR.apply(text, [_op(SubmissionOpKind.set_profile_route, profile=1, steps=None)])
    assert back == _TEXT


def test__set_route__version_order_created_under_signatures() -> None:
    text = _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.set_route, steps=(("author",), ("supervisor",)))])

    assert yaml.safe_load(text)["signatures"]["route"] == [["author"], ["supervisor"]]
    assert _EDITOR.describe(text).route == (("author",), ("supervisor",))


def test__set_route__runtime_slot_is_refused() -> None:
    with pytest.raises(SubmissionEditError):
        _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.set_route, steps=(("author--ivanov",),))])


def test__profiles__add_move_remove() -> None:
    head = ProfileHead("pre-defence", {"ru": "Предзащита", "en": "Pre-defence"}, {"ru": "Текст", "en": "Text"})

    text = _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.add_profile, head=head)])
    assert [p["id"] for p in _profiles(text)] == ["topic", "final", "pre-defence"]
    assert _profiles(text)[2]["items"] == []
    text = _EDITOR.apply(text, [_op(SubmissionOpKind.move_profile, profile=2, to=1)])
    assert [p["id"] for p in _profiles(text)] == ["topic", "pre-defence", "final"]
    text = _EDITOR.apply(text, [_op(SubmissionOpKind.remove_profile, profile=0)])
    assert [p["id"] for p in _profiles(text)] == ["pre-defence", "final"]
    assert "# ── точки сдачи ──\n" in text


def test__add_profile__first_profile_creates_pack_submission() -> None:
    head = ProfileHead("final", {"ru": "Защита", "en": "Defence"}, {})

    text = _EDITOR.apply('id: "1"\nlangs: [ru]\n', [_op(SubmissionOpKind.add_profile, head=head)])

    assert yaml.safe_load(text)["pack_submission"]["profiles"] == [
        {"id": "final", "name": {"ru": "Защита", "en": "Defence"}, "items": []}
    ]
    _parse_submission_profile(_profiles(text)[0])


def test__move_entry__keeps_the_comment_with_its_entry() -> None:
    add = _op(
        SubmissionOpKind.add_entry,
        profile=0,
        entries=SubmissionList.items,
        value={"doc_id": "report", "signatures": ["author"]},
    )
    text = _EDITOR.apply(_TEXT, [add])

    text = _EDITOR.apply(text, [_op(SubmissionOpKind.move_entry, profile=0, entries=SubmissionList.items, index=0, to=1)])

    items = _profiles(text)[0]["items"]
    assert [i["doc_id"] for i in items] == ["report", "proposal"]
    assert "        # Заявку подписывает руководитель.\n        - doc_id: proposal\n" in text


def test__apply__existing_problem_does_not_block_other_edits() -> None:
    broken = _TEXT.replace("          signatures: [author]\n", "          signatures: [author]\n          methods: wrong\n")
    head = ProfileHead("topic", {"ru": "Заявка КП", "en": "Application"}, {"ru": "Заявка на тему", "en": "Topic"})

    text = _EDITOR.apply(broken, [_op(SubmissionOpKind.set_profile, profile=0, head=head)])

    assert _profiles(text)[0]["name"]["ru"] == "Заявка КП"


def test__apply__unknown_profile_or_entry_is_an_edit_error() -> None:
    with pytest.raises(SubmissionEditError, match="no profile"):
        _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.remove_profile, profile=5)])
    with pytest.raises(SubmissionEditError, match="no entry"):
        _EDITOR.apply(_TEXT, [_op(SubmissionOpKind.remove_entry, profile=1, entries=SubmissionList.items, index=3)])


def test__apply__bad_when_is_refused() -> None:
    op = _op(
        SubmissionOpKind.add_entry,
        profile=0,
        entries=SubmissionList.signing_slots,
        value={"doc_id": "proposal", "slot_id": "author", "when": {"person": "author"}},
    )

    with pytest.raises(SubmissionEditError, match="when.person"):
        _EDITOR.apply(_TEXT, [op])
