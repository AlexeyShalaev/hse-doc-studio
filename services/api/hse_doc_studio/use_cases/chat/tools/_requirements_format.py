from __future__ import annotations

from hse_doc_studio.core.enums import Lang, RequirementFormatKind
from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.requirements.get_requirements import (
    GetRequirementsOutput,
    RequirementEntry,
)

# Shared between trace_requirements / preview_requirements_format /
# set_requirements_format so all three speak about the format and the matrix in
# the same words. The tool schema (kind + id_pattern + definition_docs +
# def_pattern + ref_pattern) mirrors RequirementsFormat one-to-one.

_SAMPLE_LIMIT = 20

FORMAT_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["macro", "id", "custom"],
            "description": (
                "macro — \\req{ID}{текст} в документах-источниках и \\reqref{ID} в остальных; "
                "id — id_pattern ловит голые ID (определения в definition_docs, ссылки в прочих); "
                "custom — свои def_pattern и ref_pattern."
            ),
        },
        "id_pattern": {
            "type": "string",
            "description": 'kind=id: regex одного идентификатора требования, напр. "ТЗ-Ф-\\d+".',
        },
        "definition_docs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "kind=id: id документов, где ID = определения (остальные = ссылки), "
            'напр. ["technical_specification"].',
        },
        "def_pattern": {
            "type": "string",
            "description": "kind=custom: regex определения с именованной группой (?P<id>…) и опц. (?P<title>…).",
        },
        "ref_pattern": {
            "type": "string",
            "description": "kind=custom: regex ссылки с именованной группой (?P<ids>…).",
        },
    },
    "required": ["kind"],
}


def format_from_args(args: dict[str, object], lang: Lang = Lang.ru) -> RequirementsFormat:
    """Build a RequirementsFormat from agent tool args.

    Raises ValueError for an unknown kind so the tool can return a clear message;
    regex validity is checked later by RequirementMatchingService.compile.
    """
    kind_raw = str(args.get("kind") or "").strip()
    try:
        kind = RequirementFormatKind(kind_raw)
    except ValueError as exc:
        message = (
            f"unknown kind «{kind_raw}»: expected macro | id | custom"
            if lang == Lang.en
            else f"неизвестный kind «{kind_raw}»: ожидается macro | id | custom"
        )
        raise ValueError(message) from exc
    return RequirementsFormat(
        kind=kind,
        id_pattern=_opt_str(args.get("id_pattern")),
        definition_docs=_str_tuple(args.get("definition_docs")),
        def_pattern=_opt_str(args.get("def_pattern")),
        ref_pattern=_opt_str(args.get("ref_pattern")),
    )


def describe_format(fmt: RequirementsFormat, lang: Lang = Lang.ru) -> str:
    """One-line human description of a resolved format, for the user."""
    if fmt.kind is RequirementFormatKind.id:
        if fmt.definition_docs:
            docs = ", ".join(fmt.definition_docs)
        else:
            docs = "tz (default)" if lang == Lang.en else "tz (по умолчанию)"
        return (
            f"id pattern «{fmt.id_pattern or '—'}», source documents: {docs}"
            if lang == Lang.en
            else f"id-паттерн «{fmt.id_pattern or '—'}», документы-источники: {docs}"
        )
    if fmt.kind is RequirementFormatKind.custom:
        return (
            f"custom regex (def: «{fmt.def_pattern or '—'}», ref: «{fmt.ref_pattern or '—'}»)"
            if lang == Lang.en
            else f"свои regex (def: «{fmt.def_pattern or '—'}», ref: «{fmt.ref_pattern or '—'}»)"
        )
    return "\\req{ID}{text} / \\reqref{ID} macros" if lang == Lang.en else "макросы \\req{ID}{текст} / \\reqref{ID}"


def summarize_matrix(out: GetRequirementsOutput, lang: Lang = Lang.ru) -> str:
    """Counts + a capped sample of the traceability matrix for a tool result."""
    items = out.items
    if not items:
        return (
            "No requirements found in the project sources for this format."
            if lang == Lang.en
            else "Требований не найдено в исходниках проекта по этому формату."
        )
    warns = sum(1 for i in items if i.status == "warn")
    errs = sum(1 for i in items if i.status == "err")
    ok = len(items) - warns - errs
    header = (
        f"Requirements: {len(items)} (covered: {ok}, no references: {warns}, no definition: {errs})"
        if lang == Lang.en
        else f"Требований: {len(items)} (покрыто: {ok}, без ссылок: {warns}, без определения: {errs})"
    )
    lines = [format_entry(item, lang) for item in items[:_SAMPLE_LIMIT]]
    if len(items) > _SAMPLE_LIMIT:
        rest = len(items) - _SAMPLE_LIMIT
        lines.append(f"… {rest} more" if lang == Lang.en else f"… ещё {rest}")
    return f"{header}\n" + "\n".join(lines)


def format_entry(item: RequirementEntry, lang: Lang = Lang.ru) -> str:
    refs = ", ".join(item.referenced_in) if item.referenced_in else "—"
    return (
        f"- [{item.status}] {item.id}: defined in «{item.source or '?'}», used in: {refs}"
        if lang == Lang.en
        else f"- [{item.status}] {item.id}: определено в «{item.source or '?'}», используется в: {refs}"
    )


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    return text or None


def _str_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        return ()
    return tuple(p.strip() for p in parts if p and p.strip())
