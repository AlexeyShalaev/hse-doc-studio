"""Точечные правки YAML (template-studio.md, D11): меняется только фрагмент узла, остальное байт в байт."""

from __future__ import annotations

from datetime import date

import pytest
import yaml
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlEditError, delete, insert_item, move_item, set_value

DOC = """\
# Шапка файла

id: "2026.1.5"
status: stable   # хвостовой комментарий
title: 'Курсовой проект'
engine:
  default: xelatex
  allowed: [xelatex]
fields:
  year:
    type:        string
    label:       { ru: Учебный год, en: Year }
    placeholder: "2027"

  # Поле города
  city:
    type:        string
    label:       { ru: Город, en: City }
    placeholder: Москва
notes: |
  первая строка
  вторая строка
items:
  - a
  # про b
  - b
  - c
slots:
  - { doc_id: report, slot_id: author }
empty: []
"""


def _changed(before: str, after: str) -> tuple[list[str], list[str]]:
    old, new = before.splitlines(), after.splitlines()
    return [line for line in old if line not in new], [line for line in new if line not in old]


@pytest.mark.parametrize(
    ("path", "value", "line"),
    [
        (("id",), "2026.1.6", 'id: "2026.1.6"'),
        (("status",), "beta", "status: beta   # хвостовой комментарий"),
        (("title",), "КП", "title: 'КП'"),
        (("fields", "year", "placeholder"), "2028", 'placeholder: "2028"'),
        (("fields", "city", "placeholder"), "Пермь", "placeholder: Пермь"),
        (("fields", "city", "label", "ru"), "Город, год", 'label:       { ru: "Город, год", en: City }'),
        (("engine", "allowed", 0), "lualatex", "allowed: [lualatex]"),
    ],
)
def test_scalar_keeps_style_and_neighbours(path: tuple, value: str, line: str) -> None:
    edited = set_value(DOC, path, value)
    removed, added = _changed(DOC, edited)
    assert len(removed) == 1
    assert [a.strip() for a in added] == [line]
    assert set_value(edited, path, _get(DOC, path)) == DOC


def _get(text: str, path: tuple) -> object:
    node = yaml.safe_load(text)
    for key in path:
        node = node[key]
    return node


def test_plain_value_that_reads_as_another_type_is_quoted() -> None:
    edited = set_value(DOC, ("fields", "city", "placeholder"), "2027")
    assert 'placeholder: "2027"' in edited
    edited = set_value(DOC, ("fields", "city", "placeholder"), "a: b # c")
    assert _get(edited, ("fields", "city", "placeholder")) == "a: b # c"


def test_non_string_scalars() -> None:
    edited = set_value(DOC, ("status",), True)
    assert "status: true   # хвостовой комментарий" in edited
    edited = set_value(DOC, ("status",), date(2026, 11, 14))
    assert _get(edited, ("status",)) == date(2026, 11, 14)
    edited = set_value(DOC, ("status",), "2026-11-14")
    assert _get(edited, ("status",)) == "2026-11-14"


def test_literal_block_scalar_keeps_its_style() -> None:
    edited = set_value(DOC, ("notes",), "одна\nдве\nтри\n")
    assert "notes: |\n  одна\n  две\n  три\nitems:" in edited
    assert set_value(edited, ("notes",), "первая строка\nвторая строка\n") == DOC
    stripped = set_value(DOC, ("notes",), "без перевода строки")
    assert _get(stripped, ("notes",)) == "без перевода строки"
    assert set_value(stripped, ("notes",), "первая строка\nвторая строка\n") == DOC


def test_zero_edit_is_byte_identical() -> None:
    assert set_value(DOC, (), yaml.safe_load(DOC)) == DOC
    assert set_value(DOC, ("fields",), _get(DOC, ("fields",))) == DOC


def test_new_key_goes_to_the_end_of_its_block_aligned_with_neighbours() -> None:
    edited = set_value(DOC, ("fields", "year", "help"), {"ru": "Год", "en": "Year"})
    assert '    placeholder: "2027"\n    help:        { ru: Год, en: Year }\n\n  # Поле города' in edited
    assert delete(edited, ("fields", "year", "help")) == DOC


def test_new_entry_in_a_blank_separated_block_gets_a_blank_line() -> None:
    edited = set_value(DOC, ("fields", "udc"), {"type": "string", "label": {"ru": "УДК", "en": "UDC"}})
    assert "    placeholder: Москва\n\n  udc:\n    type: string\n    label: { ru: УДК, en: UDC }\nnotes:" in edited
    assert delete(edited, ("fields", "udc")) == DOC


def test_new_key_after_a_sibling() -> None:
    edited = set_value(DOC, ("release",), {"kind": "patch"}, after="status")
    assert "status: stable   # хвостовой комментарий\nrelease: { kind: patch }\ntitle:" in edited
    assert delete(edited, ("release",)) == DOC
    flow = set_value(DOC, ("fields", "city", "label", "de"), "Stadt", after="ru")
    assert "label:       { ru: Город, de: Stadt, en: City }" in flow
    # Ключ уже есть или соседа нет: `after` ничего не меняет.
    assert set_value(DOC, ("status",), "beta", after="title") == DOC.replace("status: stable", "status: beta")
    assert set_value(DOC, ("zz",), 1, after="nope").endswith("zz: 1\n")


def test_new_key_in_flow_mapping() -> None:
    edited = set_value(DOC, ("fields", "city", "label", "de"), "Stadt")
    assert "label:       { ru: Город, en: City, de: Stadt }" in edited
    assert delete(edited, ("fields", "city", "label", "de")) == DOC


def test_mapping_is_edited_key_by_key() -> None:
    value = {"type": "select", "label": {"ru": "Город", "en": "Town"}, "options": ["Москва"]}
    edited = set_value(DOC, ("fields", "city"), value)
    assert "  # Поле города\n  city:\n    type:        select\n" in edited
    assert "label:       { ru: Город, en: Town }" in edited
    assert "    options:     [Москва]\nnotes:" in edited
    assert "placeholder: Москва" not in edited


def test_kind_change_rewrites_the_node() -> None:
    edited = set_value(DOC, ("status",), {"value": "beta", "since": "2026.1.6"})
    assert _get(edited, ("status",)) == {"value": "beta", "since": "2026.1.6"}
    edited = set_value(DOC, ("engine",), "xelatex")
    assert "engine: xelatex\nfields:" in edited
    edited = set_value(DOC, ("slots", 0), {"doc_id": "report", "slot_id": "author", "deep": [{"a": 1}]})
    assert "  - { doc_id: report, slot_id: author, deep: [{ a: 1 }] }\nempty:" in edited
    edited = set_value(DOC, ("items", 0), {"id": "a", "items": [{"doc_id": "report"}]})
    assert "items:\n  - id: a\n    items:\n      - { doc_id: report }\n  # про b" in edited
    edited = set_value(DOC, ("empty",), [{"id": "a", "items": [{"doc_id": "report"}]}])
    assert "empty:\n  - id: a\n    items:\n      - { doc_id: report }\n" in edited


def test_delete_takes_the_comment_above() -> None:
    edited = delete(DOC, ("items", 1))
    assert "items:\n  - a\n  - c\n" in edited
    assert "про b" not in edited
    edited = delete(DOC, ("fields", "city"))
    assert "Поле города" not in edited
    assert '    placeholder: "2027"\nnotes:' in edited


def test_delete_last_entry_leaves_an_empty_collection() -> None:
    assert "slots: []\n" in delete(DOC, ("slots", 0))
    assert "allowed: []\n" in delete(DOC, ("engine", "allowed", 0))
    assert _get(delete(delete(DOC, ("engine", "allowed")), ("engine", "default")), ("engine",)) == {}


def test_insert_into_lists() -> None:
    edited = insert_item(DOC, ("items",), 1, "a2")
    assert "  - a\n  - a2\n  # про b\n  - b\n" in edited
    assert delete(edited, ("items", 1)) == DOC
    edited = insert_item(DOC, ("engine", "allowed"), 1, "lualatex")
    assert "allowed: [xelatex, lualatex]" in edited
    edited = insert_item(DOC, ("slots",), 1, {"doc_id": "report", "slot_id": "x", "when": {"person": "supervisor"}})
    assert "  - { doc_id: report, slot_id: x, when: { person: supervisor } }\nempty:" in edited
    edited = insert_item(DOC, ("empty",), 0, {"id": "a", "items": [{"doc_id": "report"}]})
    assert "empty:\n  - id: a\n    items:\n      - { doc_id: report }\n" in edited
    assert insert_item(DOC, ("empty",), 0, "x").endswith("empty: [x]\n")


def test_move_item_carries_its_comment_and_moves_back() -> None:
    edited = move_item(DOC, ("items",), 1, 2)
    assert "items:\n  - a\n  - c\n  # про b\n  - b\nslots:" in edited
    assert move_item(edited, ("items",), 2, 1) == DOC
    flow = "route: [[author], [supervisor, co_supervisor], [academic]]\n"
    moved = move_item(flow, ("route",), 0, 2)
    assert moved == "route: [[supervisor, co_supervisor], [academic], [author]]\n"
    assert move_item(moved, ("route",), 2, 0) == flow
    assert move_item(DOC, ("items",), 1, 1) == DOC


def test_first_key_on_the_dash_line_gives_way_to_the_next() -> None:
    text = "items:\n  - id: a\n    type: text\n  - id: b\n"
    assert delete(text, ("items", 0, "id")) == "items:\n  - type: text\n  - id: b\n"


def test_flow_move_keeps_separators() -> None:
    text = "l: [a,b, c]\n"
    moved = move_item(text, ("l",), 0, 2)
    assert moved == "l: [b,c, a]\n"
    assert move_item(moved, ("l",), 2, 0) == text


def test_bare_key_in_flow_mapping_gets_a_value() -> None:
    # Запятая в простом скаляре внутри `{...}` делит строку: «листинги)» становится ключом без значения.
    text = "label: { ru: Шрифт (код, листинги), en: Mono }\n"
    edited = set_value(text, ("label", "листинги)"), "x")
    assert edited == "label: { ru: Шрифт (код, листинги): x, en: Mono }\n"


@pytest.mark.parametrize(
    "call",
    [
        lambda: set_value(DOC, ("nope", "deeper"), 1),
        lambda: set_value(DOC, ("items", 9), 1),
        lambda: insert_item(DOC, ("items",), 9, "x"),
        lambda: insert_item(DOC, ("fields",), 0, "x"),
        lambda: move_item(DOC, ("items",), 0, 5),
        lambda: delete(DOC, ()),
        lambda: delete(DOC, ("missing",)),
        lambda: set_value("a: [unclosed\n", ("a",), 1),
    ],
)
def test_bad_edits_raise(call: object) -> None:
    with pytest.raises(YamlEditError):
        call()  # type: ignore[operator]


def test_empty_document_gets_a_key() -> None:
    assert set_value("", ("id",), "x") == "id: x\n"
