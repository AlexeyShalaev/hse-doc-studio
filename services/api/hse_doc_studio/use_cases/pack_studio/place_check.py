"""Места подписей на PDF предпросмотра глазами агента (pack-studio-mcp.md, раздел 4): картинка и проверка.

Рамки мест сборки берутся тем же путём, что `GET .../signatures?build_id=` (`PackPlacesService.get`: модель мест по
якорям сборки), PDF и якоря сборки тем же `PackPreviewService`, что маршруты `previews/{id}/pdf` и `anchors`. Страницы
разбирает и рисует порт `IPdfPages`; правила проверки в `core/pack_studio/sign_check.py`. Только чтение.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import AnchorPlace, SignatureDefaultDate, SignatureDefaultPlacement
from hse_doc_studio.core.enums import AnchorState
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.places import DocFrame, SlotPlaces
from hse_doc_studio.core.pack_studio.protocols import IPdfPages, Mark, MarkKind
from hse_doc_studio.core.pack_studio.sign_check import (
    Line,
    LineSource,
    PageLayout,
    Place,
    PlaceKind,
    Rect,
    SlotCheck,
    check_places,
    is_caption,
    label_words,
    sign_rect,
)
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchors, author_anchor_id, split_author_name
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, resolve_mark, resolve_place
from hse_doc_studio.core.team import OWNER_SEPARATOR, split_instance_id
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService, PlacesView
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, version_ref

# Растр для доли чернил: хватает, чтобы увидеть рисунок под рамкой, и быстро.
INK_DPI: Final = 72
MAX_RENDER_PAGES: Final = 4


@dataclass(frozen=True)
class PlaceInspection:
    """Места сборки и что о них знает PDF: рамки, слоты без рамки, якоря, разобранные страницы и находки."""

    view: PlacesView
    document: str
    page_count: int
    places: tuple[Place, ...]
    missing: tuple[tuple[str, str], ...]
    anchors: Mapping[str, tuple[int, Line]]
    date_anchors: tuple[tuple[int, Line], ...]
    layouts: Mapping[int, PageLayout]
    checks: tuple[SlotCheck, ...]


@dataclass(frozen=True)
class RenderedPage:
    page: int
    png: bytes


def _pick(label: Mapping[str, str]) -> str:
    lang = current_interface_language().value
    return label.get(lang) or label.get("ru") or next(iter(label.values()), "")


@dataclass(frozen=True)
class _SlotFrame:
    """Рамка слота на сборке: у слота `per_author` со строками на каждого автора по рамке на автора (15.17.20)."""

    slot: str
    label: str
    box: SignatureDefaultPlacement | None
    anchor: str | None
    anchor_state: AnchorState | None
    dates: tuple[SignatureDefaultDate | None, ...]


def _authors(slot: SlotPlaces, frame: DocFrame, anchors: BuildAnchors | None) -> list[_SlotFrame]:
    """Рамки слота на документе сборки. Слот `per_author` на сборке, где шаблон ставит строку на каждого автора
    (`author__<слаг>`, signing-route.md, 15.17.20), даёт рамку каждому автору: слот `author--<слаг>`, якорь
    `author__<слаг>`, как место из пака встанет в командном проекте. Иначе одна рамка слота, как её посчитала модель
    мест."""
    label = _pick(slot.label)
    entry = frame.entry
    keys = anchors.author_keys(entry.anchor) if anchors is not None and isinstance(entry, AnchorPlace) else ()
    if not slot.per_author or not keys or anchors is None or not isinstance(entry, AnchorPlace):
        return [
            _SlotFrame(
                slot=slot.id,
                label=label,
                box=frame.box,
                anchor=entry.anchor if isinstance(entry, AnchorPlace) else None,
                anchor_state=frame.anchor.state if frame.anchor is not None else None,
                dates=tuple(mark.box for mark in frame.dates),
            )
        ]
    result: list[_SlotFrame] = []
    for key in keys:
        src = SourceAnchors(anchors.for_author(key))
        box = resolve_place(entry, src)
        result.append(
            _SlotFrame(
                slot=f"{slot.id}{OWNER_SEPARATOR}{key}",
                label=f"{label} — {key}",
                box=box,
                anchor=author_anchor_id(entry.anchor, key),
                anchor_state=AnchorState.found if src.line(entry.anchor) is not None else AnchorState.missing,
                dates=tuple(resolve_mark(mark.entry, src) for mark in frame.dates),
            )
        )
    return result


class PackPlaceCheckService:
    def __init__(self, places: PackPlacesService, previews: PackPreviewService, pages: IPdfPages) -> None:
        self._places = places
        self._previews = previews
        self._pages = pages

    async def _pdf(self, actor: Actor, workspace_id: UUID, build_id: UUID) -> bytes:
        path = await self._previews.pdf(actor, workspace_id, build_id)
        return await asyncio.to_thread(path.read_bytes)

    async def inspect(  # noqa: C901, PLR0913 — путь версии, сборка и сбор мест
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, build_id: UUID
    ) -> tuple[PlaceInspection, bytes]:
        view = await self._places.get(actor, workspace_id, pack, template, version, build_id)
        build = view.build
        if build is None or build.document is None:
            raise PackStudioError(PackStudioErrorCode.preview_not_ready)
        _, anchors = await self._previews.places_source(
            actor, workspace_id, build_id, version_ref(pack, template, version)
        )
        data = await self._pdf(actor, workspace_id, build_id)
        places: list[Place] = []
        missing: list[tuple[str, str]] = []
        absent: list[tuple[str, str, str]] = []
        for slot in view.places.slots:
            frame = slot.document
            if frame is None:
                continue
            for author in _authors(slot, frame, anchors):
                if author.box is None:
                    if author.anchor_state is AnchorState.missing and author.anchor is not None:
                        absent.append((author.slot, author.label, author.anchor))
                    else:
                        missing.append((author.slot, author.label))
                    continue
                entry = frame.entry
                origin = "mm" if not isinstance(entry, AnchorPlace) else "anchor" if anchors is not None else "fallback"
                box = author.box
                places.append(
                    Place(
                        slot=author.slot,
                        label=author.label,
                        page=box.page,
                        rect=sign_rect(box.x_mm, box.y_mm, box.width_mm),
                        origin=origin,
                        anchor=author.anchor,
                        words=label_words(*slot.label.values()),
                    )
                )
                places.extend(
                    Place(
                        slot=author.slot,
                        label=author.label,
                        page=mark.page,
                        rect=Rect(mark.x_mm, mark.y_mm, mark.x_mm + mark.width_mm, mark.y_mm + mark.height_mm),
                        kind=PlaceKind.date,
                    )
                    for mark in author.dates
                    if mark is not None
                )
        sign_lines: dict[str, tuple[int, Line]] = {}
        date_lines: list[tuple[int, Line]] = []
        for anchor in anchors.anchors if anchors is not None else ():
            line = Line(anchor.x_mm, anchor.x_mm + anchor.width_mm, anchor.y_mm, LineSource.anchor, anchor=anchor.id)
            if anchor.kind is AnchorKind.sign:
                sign_lines.setdefault(anchor.id, (anchor.page, line))
            else:
                date_lines.append((anchor.page, line))
        count = await asyncio.to_thread(self._pages.page_count, data)
        wanted = sorted({p.page for p in places} | {page for page, _ in sign_lines.values()})
        layouts = await asyncio.to_thread(self._pages.layouts, data, wanted)
        boxes: list[tuple[int, Rect, Sequence[Rect]]] = []
        index: list[int] = []
        for i, place in enumerate(places):
            layout = layouts.get(place.page)
            if place.kind is PlaceKind.sign and layout is not None:
                blank = [w.rect for w in layout.words if is_caption(w.text) or set(w.text) == {"_"}]
                boxes.append((place.page, place.rect, blank))
                index.append(i)
        shares = await asyncio.to_thread(self._pages.ink, data, boxes, INK_DPI) if boxes else []
        ink = {i: share for i, share in zip(index, shares, strict=True) if share is not None}
        checks = check_places(places, missing, layouts, count, ink, sign_lines, absent)
        inspection = PlaceInspection(
            view=view,
            document=build.document,
            page_count=count,
            places=tuple(places),
            missing=tuple(missing),
            anchors=sign_lines,
            date_anchors=tuple(date_lines),
            layouts=layouts,
            checks=checks,
        )
        return inspection, data

    async def render(  # noqa: PLR0913 — путь версии, сборка и вид картинки
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        build_id: UUID,
        *,
        pages: Sequence[int] | None = None,
        slot: str | None = None,
        dpi: int = 80,
        suggestions: bool = True,
    ) -> tuple[PlaceInspection, list[RenderedPage]]:
        inspection, data = await self.inspect(actor, workspace_id, pack, template, version, build_id)
        chosen = [p for p in (pages or default_pages(inspection, slot)) if 1 <= p <= inspection.page_count]
        rendered: list[RenderedPage] = []
        for page in chosen[:MAX_RENDER_PAGES]:
            marks = page_marks(inspection, page, slot, suggestions=suggestions)
            png = await asyncio.to_thread(self._pages.render, data, page, dpi, marks)
            rendered.append(RenderedPage(page, png))
        return inspection, rendered


def _of_slot(place_slot: str, slot: str | None) -> bool:
    """Рамка слота `slot` (без него любого): сам слот или его автор в команде (`author--<слаг>`, 15.17.20)."""
    return slot is None or place_slot == slot or split_instance_id(place_slot)[0] == slot


def _of_anchor(anchor_id: str, slot: str | None) -> bool:
    """Якорь подписи слота `slot`: его имя или строка его автора (`author__<слаг>`)."""
    return slot is None or anchor_id == slot or split_author_name(anchor_id)[0] == slot


def default_pages(inspection: PlaceInspection, slot: str | None) -> list[int]:
    """Страницы с рамками и линиями якорей (одного слота, если он назван); без них первая."""
    pages = {p.page for p in inspection.places if _of_slot(p.slot, slot)}
    pages |= {page for sid, (page, _) in inspection.anchors.items() if _of_anchor(sid, slot)}
    pages |= {c.page for c in inspection.checks if c.page is not None and _of_slot(c.slot, slot)}
    return sorted(pages) or [1]


def page_marks(  # noqa: C901 — якоря, места и предложения
    inspection: PlaceInspection, page: int, slot: str | None, *, suggestions: bool
) -> list[Mark]:
    marks: list[Mark] = []
    for sid, (anchor_page, line) in inspection.anchors.items():
        if anchor_page == page and _of_anchor(sid, slot):
            marks.append(Mark(MarkKind.anchor, line.rect(), f"⚓ {sid}"))
    bad = {c.slot for c in inspection.checks if c.status is not None and c.status.value == "error"}
    for place in inspection.places:
        if place.page != page or not _of_slot(place.slot, slot):
            continue
        if place.kind is PlaceKind.date:
            marks.append(Mark(MarkKind.date, place.rect, f"{place.slot}: {localized_error('дата', 'date')}"))
        else:
            kind = MarkKind.problem if place.slot in bad else MarkKind.sign
            marks.append(Mark(kind, place.rect, f"{place.slot}: {place.label}"))
    if suggestions:
        marks.extend(
            Mark(MarkKind.suggested, check.suggested, f"→ {check.slot}")
            for check in inspection.checks
            if check.suggested is not None and check.line_page == page and _of_slot(check.slot, slot)
        )
    return marks
