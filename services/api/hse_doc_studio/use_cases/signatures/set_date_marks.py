"""Метки даты подписания слота документа и ручная дата подписи (docs/design/signing-route.md, 14.3 и 14.7).

`PUT .../signatures/placements/{doc_id}/{slot_id}/dates` заменяет метки даты слота документа целиком и, вне маршрута,
ставит или снимает ручную дату подписи (`SignedAt.source` `manual`). Размещения слота может ещё не быть: оно
создаётся выключенным на месте из пака, чтобы у подписи без видимой метки (PAdES) была дата.

Срез R22 правит метки только мимо маршрута. Документ, который держит идущий или завершённый маршрут, правится его
сценарием (R23): пока 409 `route_locked`. Ручная дата на паре участника маршрута 409 `date_from_route`: дату даёт
его согласие (`RecordSignedAt`, R23).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, SignedAtSource
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, RuntimeSlot, SignatureSlotService
from hse_doc_studio.core.signatures.dates import MAX_DATE_MARKS
from hse_doc_studio.core.signatures.ports import IPdfPages
from hse_doc_studio.core.signatures.stamps import date_mark_text
from hse_doc_studio.core.signing_route.entities import RouteInputError
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.core.value_objects import DateMark, SignaturePlacement, SignaturesState, SignedAt
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signatures.signing_source import source_of

logger = structlog.get_logger()

_MARK_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_NEW_ID = re.compile(r"^d(\d{1,6})$")
# Допуск на округление координат редактора: рамка, касающаяся края, остаётся на странице.
_EDGE_MM = 0.01


@dataclass(frozen=True)
class DateMarkInput:
    """Метка даты из запроса: `id` None у новой; формат и выравнивание строкой, их проверяет сценарий."""

    id: str | None
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    format: str
    align: str = DateMarkAlign.centered.value


@dataclass
class SetDateMarksInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    dates: list[DateMarkInput]
    # Ручная дата подписи: `signed_at_given` False не менять; иначе `signed_at` день ISO или None (снять).
    signed_at_given: bool = False
    signed_at: str | None = None
    # Подтверждение сброса подписей сценарием маршрута (14.6, срез R23); мимо маршрута не нужно.
    confirm_reset: bool = False


@dataclass(frozen=True)
class SetDateMarksOutput:
    placement: SignaturePlacement
    # Что напечатает каждая метка сейчас, в порядке `placement.dates`; None у пустой.
    texts: tuple[str | None, ...]


def bad_date_mark(ru: str, en: str) -> RouteInputError:
    return RouteInputError("bad_date_mark", localized_error(ru, en))


def bad_date() -> RouteInputError:
    return RouteInputError(
        "bad_date",
        localized_error(
            "Дата подписи должна быть днём в виде ГГГГ-ММ-ДД",
            "The signing date must be a day in the YYYY-MM-DD form",
        ),
    )


def _manual_day(raw: str | None) -> date | None:
    """Ручная дата подписи из запроса: день «2026-11-13»; иначе `bad_date`."""
    if raw is None:
        return None
    try:
        if len(raw) != len("2026-11-13"):
            raise ValueError(raw)
        return date.fromisoformat(raw)
    except ValueError:
        raise bad_date() from None


def _checked_shape(items: list[DateMarkInput]) -> list[tuple[DateMarkInput, DateMarkFormat, DateMarkAlign]]:
    """Число меток, формат, выравнивание и id без сведений о документе; иначе `bad_date_mark`."""
    if len(items) > MAX_DATE_MARKS:
        raise bad_date_mark(
            f"У подписи может быть не больше {MAX_DATE_MARKS} меток даты на документе",
            f"A signature can have at most {MAX_DATE_MARKS} date marks on a document",
        )
    checked: list[tuple[DateMarkInput, DateMarkFormat, DateMarkAlign]] = []
    seen: set[str] = set()
    for n, item in enumerate(items, start=1):
        try:
            fmt = DateMarkFormat(item.format)
        except ValueError:
            raise bad_date_mark(
                f"Метка даты {n}: неизвестный формат {item.format!r}",
                f"Date mark {n}: unknown format {item.format!r}",
            ) from None
        try:
            align = DateMarkAlign(item.align)
        except ValueError:
            raise bad_date_mark(
                f"Метка даты {n}: неизвестное выравнивание {item.align!r}",
                f"Date mark {n}: unknown alignment {item.align!r}",
            ) from None
        if item.id is not None and (not _MARK_ID.match(item.id) or item.id in seen):
            raise bad_date_mark(
                f"Метка даты {n}: id {item.id!r} неверный или повторяется",
                f"Date mark {n}: id {item.id!r} is invalid or repeated",
            )
        if item.id is not None:
            seen.add(item.id)
        checked.append((item, fmt, align))
    return checked


def _check_frame(n: int, item: DateMarkInput, sizes: tuple[tuple[float, float], ...]) -> None:
    """Рамка на странице документа: страница есть, рамка не уходит за край. Без PDF только за левый и верхний."""
    if item.page < 1 or (sizes and item.page > len(sizes)):
        total = f" (страниц: {len(sizes)})" if sizes else ""
        total_en = f" ({len(sizes)} page(s))" if sizes else ""
        raise bad_date_mark(
            f"Метка даты {n}: страницы {item.page} нет в документе{total}",
            f"Date mark {n}: page {item.page} is not in the document{total_en}",
        )
    if item.width_mm <= 0 or item.height_mm <= 0:
        raise bad_date_mark(f"Метка даты {n}: у рамки нет размера", f"Date mark {n}: the box has no size")
    outside = item.x_mm < -_EDGE_MM or item.y_mm < -_EDGE_MM
    if sizes:
        width, height = sizes[item.page - 1]
        outside = (
            outside or item.x_mm + item.width_mm > width + _EDGE_MM or item.y_mm + item.height_mm > height + _EDGE_MM
        )
    if outside:
        raise bad_date_mark(
            f"Метка даты {n}: рамка выходит за край страницы {item.page}",
            f"Date mark {n}: the box is past the edge of page {item.page}",
        )


def _new_ids(
    checked: list[tuple[DateMarkInput, DateMarkFormat, DateMarkAlign]], old: tuple[DateMark, ...]
) -> list[str]:
    """id каждой метки: из запроса или следующий `dN` после всех известных, чтобы не путать с удалёнными."""
    taken = {item.id for item, _, _ in checked if item.id} | {mark.id for mark in old}
    numbers = [int(m.group(1)) for mark_id in taken if (m := _NEW_ID.match(mark_id))]
    next_n = max(numbers, default=0) + 1
    ids: list[str] = []
    for item, _, _ in checked:
        if item.id is not None:
            ids.append(item.id)
            continue
        while f"d{next_n}" in taken:
            next_n += 1
        ids.append(f"d{next_n}")
        taken.add(f"d{next_n}")
        next_n += 1
    return ids


class SetDateMarksUC:
    def __init__(  # noqa: PLR0913 — порты сценария перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        routes: ISigningRouteGate,
        pages: IPdfPages,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._routes = routes
        self._pages = pages
        self._slots = SignatureSlotService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: SetDateMarksInput) -> SetDateMarksOutput:
        project, version, doc, rslot = await self._load(inp)
        checked = _checked_shape(inp.dates)
        day = _manual_day(inp.signed_at) if inp.signed_at_given else None
        await self._routes.require_dates_editable(project.id, inp.doc_id, inp.slot_id, manual=inp.signed_at_given)
        async with project_lock(project):
            state = self._signature_repo.get_state(project.folder)
            sizes = await self._page_sizes(project, version, doc, state)
            for n, (item, _, _) in enumerate(checked, start=1):
                _check_frame(n, item, sizes)
            existing = state.placements.get(inp.doc_id, {}).get(inp.slot_id)
            base = existing or _seeded(rslot)
            marks = tuple(
                DateMark(
                    id=mark_id,
                    page=item.page,
                    x_mm=item.x_mm,
                    y_mm=item.y_mm,
                    width_mm=item.width_mm,
                    height_mm=item.height_mm,
                    format=fmt,
                    align=align,
                )
                for mark_id, (item, fmt, align) in zip(_new_ids(checked, base.dates), checked, strict=True)
            )
            signed_at = base.signed_at
            if inp.signed_at_given:
                signed_at = SignedAt(at=day.isoformat(), source=SignedAtSource.manual) if day is not None else None
            placement = replace(base, dates=marks, signed_at=signed_at)
            updated = state
            if placement != existing:
                doc_placements = {**state.placements.get(inp.doc_id, {}), inp.slot_id: placement}
                updated = replace(state, placements={**state.placements, inp.doc_id: doc_placements})
                self._signature_repo.save_state(project.folder, updated)
        if placement != existing:
            logger.info(
                "signature date marks set",
                project_id=str(inp.project_id),
                doc_id=inp.doc_id,
                slot=inp.slot_id,
                marks=len(marks),
                signed_at=signed_at.source.value if signed_at else None,
            )
        lang = str(project.lang)
        texts = tuple(date_mark_text(updated, inp.doc_id, inp.slot_id, mark, lang) for mark in marks)
        return SetDateMarksOutput(placement=placement, texts=texts)

    async def _load(self, inp: SetDateMarksInput) -> tuple[Project, TemplateVersion, Document, RuntimeSlot]:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )
        rslot = self._slots.find_runtime_slot(project, version, inp.slot_id)
        if rslot is None:
            raise NotFoundError(
                localized_error(
                    f"Слот {inp.slot_id!r} не определён в шаблоне проекта",
                    f"Slot {inp.slot_id!r} is not defined in the project template",
                )
            )
        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(f"Документ {inp.doc_id!r} не найден", f"Document {inp.doc_id!r} not found")
            )
        if not self._slots.slot_applies_to_doc(rslot, doc):
            raise ValueError(
                localized_error(
                    f"Слот {inp.slot_id!r} не применим к документу {inp.doc_id!r}",
                    f"Slot {inp.slot_id!r} does not apply to document {inp.doc_id!r}",
                )
            )
        return project, version, doc, rslot

    async def _page_sizes(
        self, project: Project, version: TemplateVersion, doc: Document, state: SignaturesState
    ) -> tuple[tuple[float, float], ...]:
        """Размеры страниц источника подписи (версия на подписи или сборка); пусто, если PDF ещё нет."""
        try:
            _, output_file = self._template_service.resolve_instance_source(project, doc, version)
        except (NotFoundError, ValueError):
            return ()
        compiled = project.folder / output_file if output_file else None
        source = await source_of(project.folder, compiled, state, doc.id)
        if source.path is None or not source.exists or source.path.suffix.lower() != ".pdf":
            return ()
        return await asyncio.to_thread(self._pages.page_sizes_mm, source.path)


def _seeded(rslot: RuntimeSlot) -> SignaturePlacement:
    """Выключенное размещение на месте из пака: метки даты есть и у подписи, которую не размещали (14.3)."""
    default = rslot.slot_def.default_placement
    return SignaturePlacement(
        enabled=False, page=default.page, x_mm=default.x_mm, y_mm=default.y_mm, width_mm=default.width_mm
    )
