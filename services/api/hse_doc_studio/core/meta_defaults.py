"""Pure domain logic for materialising template meta-field defaults.

A pack's `meta_fields` may declare a static `default` and/or a computed `auto`
value. Neither was ever applied — the project's `meta` dict was stored exactly
as received. These helpers fill in the blanks at project-creation time so the
compiled PDF always carries sensible values (degree type, educational
programme, defense year) even when the client sends nothing.

No I/O. "Now" is injected as a `date` so the result is deterministic/testable.
"""

from __future__ import annotations

from datetime import date
from typing import Any, assert_never

from hse_doc_studio.core.catalog import MetaFieldDef, TemplateVersion
from hse_doc_studio.core.enums import MetaFieldAuto, MetaFieldType

# Only textual fields get a default/auto pre-fill. `bool` (e.g. nda) and `person`
# fields have dedicated handling elsewhere and must not be materialised here.
# `font` is textual (its value is a family-name string), so its `default` (e.g.
# Times New Roman) is materialised here too.
_TEXTUAL_TYPES = (MetaFieldType.string, MetaFieldType.select, MetaFieldType.font)

# HSE academic year starts on September 1: from September onwards the running
# academic year ends (graduation/defense happens) in the NEXT calendar year.
_ACADEMIC_YEAR_START_MONTH = 9


def academic_year_end(today: date) -> int:
    """End year of the HSE academic year containing `today` (the defense year).

    Sep–Dec -> next calendar year; Jan–Aug -> current. So Sep 2025 -> 2026,
    Feb 2026 -> 2026, Jun 2026 -> 2026.
    """
    return today.year + 1 if today.month >= _ACADEMIC_YEAR_START_MONTH else today.year


def resolve_auto(auto: MetaFieldAuto, today: date) -> str:
    """Compute the value for an `auto` meta field as of `today`."""
    if auto is MetaFieldAuto.academic_year:
        return str(academic_year_end(today))
    assert_never(auto)  # exhaustiveness guard for future MetaFieldAuto members


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def field_default(field: MetaFieldDef, today: date) -> Any | None:
    """The value to pre-fill for a field when blank: `auto` wins over `default`.

    Non-textual fields (bool/person) are never pre-filled here.
    """
    if field.type not in _TEXTUAL_TYPES:
        return None
    if field.auto is not None:
        return resolve_auto(field.auto, today)
    return field.default


def apply_meta_defaults(version: TemplateVersion, meta: dict[str, Any], today: date) -> dict[str, Any]:
    """Return a copy of `meta` with template defaults/auto filled for blank keys.

    Only blank (missing / None / empty-string) values are touched, so any value
    the user actually supplied is preserved verbatim.
    """
    result = dict(meta)
    for field_id, field in version.meta_fields.items():
        if not _is_blank(result.get(field_id)):
            continue
        value = field_default(field, today)
        if value is not None:
            result[field_id] = value
    return result
