from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from hse_doc_studio.core.catalog import MetaFieldDef
from hse_doc_studio.core.enums import MetaFieldAuto, MetaFieldType, RequiredAt
from hse_doc_studio.core.meta_defaults import (
    academic_year_end,
    apply_meta_defaults,
    field_default,
    resolve_auto,
)

from tests.factories import make_template_version


def _field(
    *,
    type_: MetaFieldType = MetaFieldType.string,
    default: object | None = None,
    auto: MetaFieldAuto | None = None,
    required_at: RequiredAt = RequiredAt.create,
) -> MetaFieldDef:
    return MetaFieldDef(
        type=type_,
        label={"ru": "Поле", "en": "Field"},
        placeholder=None,
        required_at=required_at,
        help=None,
        default=default,
        auto=auto,
    )


def _version(meta_fields: dict[str, MetaFieldDef]):
    return dataclasses.replace(make_template_version(), meta_fields=meta_fields)


# --- academic_year_end ------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2025, 9, 1), 2026),  # academic year just started -> defense next year
        (date(2025, 10, 15), 2026),
        (date(2025, 12, 31), 2026),
        (date(2026, 1, 1), 2026),  # same academic year, defense this year
        (date(2026, 2, 15), 2026),
        (date(2026, 6, 18), 2026),
        (date(2026, 8, 31), 2026),  # last day before the new academic year
        (date(2026, 9, 1), 2027),  # rolls over
    ],
)
def test__academic_year_end__various_dates__returns_expected_defense_year(today: date, expected: int) -> None:
    assert academic_year_end(today) == expected


@pytest.mark.unit
def test__resolve_auto__academic_year__returns_year_as_string() -> None:
    assert resolve_auto(MetaFieldAuto.academic_year, date(2025, 9, 1)) == "2026"


# --- field_default ----------------------------------------------------------


@pytest.mark.unit
def test__field_default__static_default_only__returns_default() -> None:
    field = _field(default="Бакалавриат")
    assert field_default(field, date(2026, 1, 1)) == "Бакалавриат"


@pytest.mark.unit
def test__field_default__auto_and_default_both_set__auto_wins() -> None:
    field = _field(default="2000", auto=MetaFieldAuto.academic_year)
    assert field_default(field, date(2025, 9, 1)) == "2026"


@pytest.mark.unit
def test__field_default__non_textual_field_types__returns_none() -> None:
    # A bool field (e.g. nda) with a default must never be materialised as text.
    assert field_default(_field(type_=MetaFieldType.bool_, default=False), date(2026, 1, 1)) is None
    assert field_default(_field(type_=MetaFieldType.person), date(2026, 1, 1)) is None


# --- apply_meta_defaults ----------------------------------------------------


@pytest.mark.unit
def test__apply_meta_defaults__blank_values__fills_static_default_and_auto() -> None:
    version = _version(
        {
            "degree_type": _field(default="Бакалавриат"),
            "specialization": _field(default="Программная инженерия"),
            "year": _field(auto=MetaFieldAuto.academic_year),
        }
    )
    result = apply_meta_defaults(version, {}, date(2025, 9, 1))
    assert result == {
        "degree_type": "Бакалавриат",
        "specialization": "Программная инженерия",
        "year": "2026",
    }


@pytest.mark.unit
def test__apply_meta_defaults__user_provided_values__preserves_them() -> None:
    version = _version(
        {
            "degree_type": _field(default="Бакалавриат"),
            "year": _field(auto=MetaFieldAuto.academic_year),
        }
    )
    result = apply_meta_defaults(version, {"degree_type": "Магистратура", "year": "2030"}, date(2025, 9, 1))
    assert result["degree_type"] == "Магистратура"
    assert result["year"] == "2030"


@pytest.mark.unit
def test__apply_meta_defaults__whitespace_only_or_empty_value__treated_as_blank_and_filled() -> None:
    # Empty / whitespace-only values are treated as blank and get the default.
    version = _version({"degree_type": _field(default="Бакалавриат")})
    assert apply_meta_defaults(version, {"degree_type": "  "}, date(2026, 1, 1))["degree_type"] == "Бакалавриат"
    assert apply_meta_defaults(version, {"degree_type": ""}, date(2026, 1, 1))["degree_type"] == "Бакалавриат"


@pytest.mark.unit
def test__apply_meta_defaults__bool_field__skips_it() -> None:
    version = _version({"nda": _field(type_=MetaFieldType.bool_, default=False, required_at=RequiredAt.never)})
    assert apply_meta_defaults(version, {}, date(2026, 1, 1)) == {}


@pytest.mark.unit
def test__field_default__font_type__materialises_default_but_none_when_absent() -> None:
    # `font` is textual: its default (e.g. Times New Roman) must be pre-filled,
    # while a font field with no default (e.g. mono → resolved in LaTeX) stays None.
    assert (
        field_default(_field(type_=MetaFieldType.font, default="Times New Roman"), date(2026, 1, 1))
        == "Times New Roman"
    )
    assert field_default(_field(type_=MetaFieldType.font, required_at=RequiredAt.never), date(2026, 1, 1)) is None


@pytest.mark.unit
def test__apply_meta_defaults__font_fields__fills_font_main_but_not_font_mono() -> None:
    version = _version(
        {
            "font_main": _field(type_=MetaFieldType.font, default="Times New Roman", required_at=RequiredAt.never),
            "font_mono": _field(type_=MetaFieldType.font, required_at=RequiredAt.never),
        }
    )
    result = apply_meta_defaults(version, {}, date(2026, 1, 1))
    assert result == {"font_main": "Times New Roman"}


@pytest.mark.unit
def test__apply_meta_defaults__called_with_input_dict__does_not_mutate_it() -> None:
    version = _version({"degree_type": _field(default="Бакалавриат")})
    original: dict[str, object] = {}
    apply_meta_defaults(version, original, date(2026, 1, 1))
    assert original == {}
