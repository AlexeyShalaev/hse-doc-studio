"""Места подписей агентом (pack-studio-mcp.md, раздел 4): картинка страницы с рамками и автоматическая проверка.

`pack_signature_render` отдаёт PNG страниц PDF сборки предпросмотра с рамками мест (MCP `ImageContent`), чтобы
мультимодальный агент посмотрел сам; `pack_signature_check` проверяет каждое место по тексту, линиям и растру страницы
и предлагает готовые операции для `pack_set_placement`. Оба только читают, сценарий `PackPlaceCheckService`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolImage, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.pack_studio.sign_check import Code, Finding, Place, PlaceKind, Rect, SlotCheck, line_data
from hse_doc_studio.core.team import OWNER_SEPARATOR
from hse_doc_studio.use_cases.mcp.tools._base import bool_arg, int_arg, optional_text, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_view import FORMAT_PROP, layout_arg, layout_result
from hse_doc_studio.use_cases.mcp.tools.packs import _VERSION, _WORKSPACE_ID, PackTool, _pages, _schema, version_arg
from hse_doc_studio.use_cases.pack_studio.place_check import PackPlaceCheckService, PlaceInspection

DEFAULT_DPI: Final = 80
_BUILD = {"type": "string", "description": "Id сборки предпросмотра этой версии из pack_preview_build (succeeded)"}

# Что значит находка, словами для человека и агента: {числа} из данных находки.
_TEXTS: Final[Mapping[Code, tuple[str, str]]] = {
    Code.no_place: (
        "Места нет: якорь записи не найден в сборке, рамка за краем листа или места нет совсем.",
        "No place: the entry's anchor is missing in the build, the box is off the sheet, or there is no place.",
    ),
    Code.anchor_missing: (
        (
            "В этой сборке нет строки слота (якорь «{anchor}»): при этих данных или в этом варианте документа шаблон "
            "её не печатает, место не ставится. Проверьте сборку, где строка есть."
        ),
        (
            "This build has no line for the slot (anchor «{anchor}»): the template does not print it for this data or "
            "this document variant, so there is no place. Check a build where the line is printed."
        ),
    ),
    Code.page_out_of_range: (
        "Страница {page} больше числа страниц PDF ({pages}).",
        "Page {page} is past the PDF end ({pages}).",
    ),
    Code.outside_page: ("Рамка выходит за лист.", "The box goes off the sheet."),
    Code.near_edge: (
        "Рамка ближе {margin_mm} мм к краю листа: принтер может обрезать.",
        "The box is closer than {margin_mm} mm to the sheet edge: a printer may cut it.",
    ),
    Code.overlaps_text: ("Рамка закрывает текст: «{text}».", "The box covers text: «{text}»."),
    Code.overlaps_place: ("Рамка пересекает место {slots}.", "The box overlaps the place of {slots}."),
    Code.busy_area: (
        "Под рамкой рисунок или таблица ({ink} площади тёмная).",
        "There is a drawing or table under the box ({ink} of the area is dark).",
    ),
    Code.far_from_line: (
        "Рамка не на своей строке подписи: линия {line}.",
        "The box is not on its signature line: line {line}.",
    ),
    Code.no_line: (
        "Рядом нет строки подписи (линии, подчёркиваний, якоря): проверьте по картинке.",
        "No signature line nearby (rule, underscores, anchor): check the picture.",
    ),
    Code.anchor_available: (
        "У шаблона есть якорь строки этого слота: место на якоре переживёт правку текста (bind_anchor).",
        "The template has an anchor line for this slot: a place on the anchor survives text edits (bind_anchor).",
    ),
}


def _mm(rect: Rect | None) -> dict[str, float] | None:
    if rect is None:
        return None
    return {"x_mm": round(rect.x0, 1), "y_mm": round(rect.y0, 1), "width_mm": round(rect.width, 1)}


def _say(finding: Finding) -> str:
    ru, en = _TEXTS[finding.code]
    template = en if current_interface_language().value == "en" else ru
    data = dict(finding.data)
    if "line" in data and isinstance(data["line"], Mapping):
        line = data["line"]
        data["line"] = f"{line.get('x0_mm')}..{line.get('x1_mm')} мм, y {line.get('y_mm')} мм ({line.get('source')})"
        if "line_page" in data:
            data["line"] = f"{data['line']}, стр. {data['line_page']}"
    if "slots" in data and isinstance(data["slots"], list):
        data["slots"] = ", ".join(str(s) for s in data["slots"])
    if "ink" in data and isinstance(data["ink"], float):
        data["ink"] = f"{round(data['ink'] * 100)} %"
    try:
        return template.format(**data)
    except (KeyError, IndexError):
        return template


def _ops(check: SlotCheck, document: str) -> list[dict[str, Any]]:
    """Готовые операции для `pack_set_placement`: на якорь, если он есть, иначе предложенная рамка в мм."""
    if check.slot.endswith(".date") or OWNER_SEPARATOR in check.slot:
        # Рамка автора команды (`author--<слаг>`): запись пака одна на всех авторов, её двигают по рамке слота.
        return []
    if check.bind_anchor:
        return [{"op": "bind_anchor", "slot": check.slot, "doc": document}]
    if check.suggested is not None and check.line_page is not None:
        box = _mm(check.suggested) or {}
        return [{"op": "set_place", "slot": check.slot, "doc": document, "box": {"page": check.line_page, **box}}]
    return []


def check_data(inspection: PlaceInspection) -> dict[str, Any]:
    document = inspection.document
    slots = []
    all_ops: list[dict[str, Any]] = []
    for check in inspection.checks:
        ops = _ops(check, document)
        all_ops += ops
        slots.append(
            {
                "slot": check.slot,
                "label": check.label,
                "status": check.status.value if check.status is not None else "ok",
                "page": check.page,
                "box": _mm(check.rect),
                "line": line_data(check.line),
                "findings": [
                    {"code": f.code.value, "severity": f.severity.value, "text": _say(f), **dict(f.data)}
                    for f in check.findings
                ],
                "suggested": {"page": check.line_page, **(_mm(check.suggested) or {})} if check.suggested else None,
                "suggested_ops": ops,
            }
        )
    errors = sum(1 for s in slots if s["status"] == "error")
    warnings = sum(1 for s in slots if s["status"] == "warning")
    return {
        "version": inspection.view.ref.dir,
        "document": document,
        "pages": inspection.page_count,
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "anchors_known": inspection.view.places.anchors_known,
        "slots": slots,
        "suggested_ops": all_ops,
    }


def check_text(data: Mapping[str, Any]) -> str:
    en = current_interface_language().value == "en"
    where_doc = f"{data['document']} ({data['version']})"
    head = (
        f"Signature places of {where_doc}: errors {data['errors']}, warnings {data['warnings']}"
        if en
        else f"Места подписей {where_doc}: ошибок {data['errors']}, замечаний {data['warnings']}"
    )
    lines = [head]
    for slot in data["slots"]:
        box = slot["box"]
        where = f"p. {slot['page']}, x {box['x_mm']}, y {box['y_mm']}, w {box['width_mm']} mm" if box else "-"
        lines.append(f"- {slot['slot']} ({slot['label']}): {slot['status']}; {where}")
        lines += [f"    [{f['severity']}] {f['code']}: {f['text']}" for f in slot["findings"]]
        if slot["suggested_ops"]:
            lines.append(f"    pack_set_placement ops: {slot['suggested_ops']}")
    if data["suggested_ops"]:
        lines.append(
            "Apply: pack_set_placement with build_id and these ops, then check again."
            if en
            else "Применить: pack_set_placement с build_id и этими ops, затем проверить снова."
        )
    return "\n".join(lines)


def _box(place: Place) -> dict[str, float] | None:
    box = _mm(place.rect)
    if box is not None and place.kind is PlaceKind.date:
        box["height_mm"] = round(place.rect.height, 1)
    return box


def _legend(inspection: PlaceInspection, pages: Sequence[int]) -> list[dict[str, Any]]:
    legend: list[dict[str, Any]] = [
        {
            "slot": place.slot,
            "label": place.label,
            "kind": place.kind.value,
            "page": place.page,
            "box": _box(place),
            "origin": place.origin,
        }
        for place in inspection.places
        if place.page in pages
    ]
    legend += [
        {"slot": slot, "kind": "anchor", "page": page, "line": line_data(line)}
        for slot, (page, line) in inspection.anchors.items()
        if page in pages
    ]
    return legend


class PackSignatureRenderTool(PackTool):
    spec = ToolSpec(
        name="pack_signature_render",
        description=(
            "Студия шаблонов: картинка страниц PDF сборки предпросмотра с местами подписей поверх, чтобы посмотреть "
            "глазами. Синие рамки подписи «слот: подпись», красные рамки с ошибкой проверки, зелёные метки даты, "
            "оранжевый пунктир линии якорей, фиолетовые предложенные рамки (suggestions). Слот per_author на общем "
            "документе команды с якорями author__<слаг> рисуется рамкой на автора (author--<слаг>). По умолчанию "
            "страницы с рамками и якорями, не больше 4; pages как «1» или «1,3». Текст ответа: легенда в мм. Порядок: "
            "pack_preview_build, pack_signature_render, pack_signature_check, pack_set_placement, снова render."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "version": _VERSION,
                "build_id": _BUILD,
                "pages": {"type": "string", "description": "Страницы: «1», «1-2» или «1,3»"},
                "slot": {"type": "string", "description": "Только места этого слота"},
                "dpi": {"type": "integer", "default": DEFAULT_DPI, "description": "Разрешение картинки, 50..150"},
                "suggestions": {"type": "boolean", "default": True, "description": "Рисовать предложенные рамки"},
            },
            ("workspace_id", "version", "build_id"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        service = await self._deps.get(PackPlaceCheckService)
        inspection, rendered = await service.render(
            actor,
            uuid_arg(args, "workspace_id"),
            ref.pack,
            ref.template,
            ref.version,
            uuid_arg(args, "build_id"),
            pages=_pages(optional_text(args, "pages")),
            slot=optional_text(args, "slot"),
            dpi=int_arg(args, "dpi", DEFAULT_DPI, lo=50, hi=150),
            suggestions=bool_arg(args, "suggestions", True),
        )
        shown = [r.page for r in rendered]
        data = {
            "version": inspection.view.ref.dir,
            "document": inspection.document,
            "pages": inspection.page_count,
            "shown": shown,
            "legend": _legend(inspection, shown),
        }
        result = layout_result("json", "", data)
        return ToolResult.ok(result.text, images=tuple(ToolImage(r.png) for r in rendered))


class PackSignatureCheckTool(PackTool):
    spec = ToolSpec(
        name="pack_signature_check",
        description=(
            "Студия шаблонов: автоматическая проверка мест подписей на PDF сборки предпросмотра. По каждому слоту "
            "документа: есть ли рамка, на той ли странице, не за краем и не у края листа, не закрывает ли текст и "
            "чужие рамки, нет ли под ней рисунка, стоит ли на своей строке подписи (якорь слота, линия, «____», "
            "подпись слота рядом). Находки с текстом и числами, предложенная рамка и готовые suggested_ops для "
            "pack_set_placement (bind_anchor, если у слота есть якорь, иначе set_place). Слот per_author на общем "
            "документе команды, где шаблон ставит строку на каждого автора (якорь author__<слаг>), проверяется рамкой "
            "на автора: author--<слаг>. Только чтение."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "version": _VERSION, "build_id": _BUILD, "format": FORMAT_PROP},
            ("workspace_id", "version", "build_id"),
        ),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        ref = version_arg(args)
        service = await self._deps.get(PackPlaceCheckService)
        inspection, _ = await service.inspect(
            actor, uuid_arg(args, "workspace_id"), ref.pack, ref.template, ref.version, uuid_arg(args, "build_id")
        )
        data = check_data(inspection)
        return layout_result(layout_arg(args), check_text(data), data)
