"""«Подпись необязательна на этой точке» (docs/design/signing-route.md, 13.3 и 13.6).

Автор отмечает место подписи документа на точке сдачи как необязательное (`SignaturesState.optional`): такую
подпись пакет не требует, а маршрут позволит пропустить её подписанта. Отметка не меняет видимый слой, снимок
маршрута и версию на подписи, поэтому пишется мимо сторожа `route_locked` и на идущем маршруте. Проверки маршрута
(какой маршрут держит документ, какие пары он включил сверх точки) сценарий берёт у `ISigningRouteGate`, подписан
ли слот и пропущен ли он, из состояния подписей.

Переходы (13.3):

- отметить можно слот, который не подписан, если документ держит маршрут (`slot_signed`), и который пак не
  запрещает (`optional_forbidden`);
- снять отметку можно всегда; если пару уже пропустили, а маршрут документ держит, пропуск остаётся до нового
  раунда (`returns_next_round`), а если не держит (отменён, снят с контроля), пропуск снимается сразу.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, SignatureSlotService, SubmissionProfileService
from hse_doc_studio.core.signatures.plan import SlotStatus, slot_state
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.core.signing_route.entities import DocSlot, RouteConflictError, RouteInputError
from hse_doc_studio.core.signing_route.ports import HeldRoute, ISigningRouteGate
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signatures.get_signature_plan import doc_facts, profile_pairs

logger = structlog.get_logger()


@dataclass
class SetSlotOptionalInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    profile_id: str
    optional: bool


@dataclass(frozen=True)
class SetSlotOptionalOutput:
    """Что стало с парой: отметка, пропуск и вернётся ли пропущенный подписант следующим раундом."""

    doc_id: str
    slot_id: str
    profile_id: str
    optional: bool
    skipped: bool
    returns_next_round: bool


def unknown_slot() -> RouteInputError:
    return RouteInputError(
        "unknown_slot",
        localized_error(
            "Эта подпись не ставится на этот документ на этой точке",
            "This signature is not placed on this document at this checkpoint",
        ),
    )


def optional_forbidden() -> RouteConflictError:
    return RouteConflictError(
        "optional_forbidden",
        localized_error(
            "Эту подпись требует шаблон: сделать её необязательной нельзя",
            "The template requires this signature: it cannot be made optional",
        ),
    )


def slot_signed() -> RouteConflictError:
    return RouteConflictError(
        "slot_signed",
        localized_error(
            "Подпись уже стоит: отметить её необязательной нельзя",
            "The signature is already in place: it cannot be made optional",
        ),
    )


def _with_optional(state: SignaturesState, doc_id: str, profile_id: str, slot_id: str, on: bool) -> SignaturesState:
    by_profile = dict(state.optional.get(doc_id, {}))
    slots = set(by_profile.get(profile_id, ()))
    if on:
        slots.add(slot_id)
    else:
        slots.discard(slot_id)
    if slots:
        by_profile[profile_id] = frozenset(slots)
    else:
        by_profile.pop(profile_id, None)
    optional = {k: v for k, v in state.optional.items() if k != doc_id}
    if by_profile:
        optional[doc_id] = by_profile
    return replace(state, optional=optional)


def _without_skip(state: SignaturesState, doc_id: str, slot_id: str) -> SignaturesState:
    by_slot = {k: v for k, v in state.skipped.get(doc_id, {}).items() if k != slot_id}
    skipped = {k: v for k, v in state.skipped.items() if k != doc_id}
    if by_slot:
        skipped[doc_id] = by_slot
    return replace(state, skipped=skipped)


class SetSlotOptionalUC:
    def __init__(  # noqa: PLR0913 — порты сценария перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        routes: ISigningRouteGate,
        audit: ISignatureAudit | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._routes = routes
        self._audit = audit
        self._slots = SignatureSlotService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: SetSlotOptionalInput) -> SetSlotOptionalOutput:
        project, version, doc = await self._load(inp)
        # Под замком проекта: маршрут пишет пропуски и придержания в то же состояние подписей.
        async with project_lock(project):
            routes = await self._routes.held_routes(project.id)
            held = next((r for r in routes if inp.doc_id in r.docs), None)
            state = self._signature_repo.get_state(project.folder)
            self._check_slot(project, version, doc, inp, routes, state)
            skip = state.skip_of(inp.doc_id, inp.slot_id, inp.profile_id)
            if inp.optional and held is not None and skip is None:
                facts = await doc_facts(project, version, doc, state, self._template_service)
                if slot_state(state, inp.doc_id, inp.slot_id, facts, profile_id=inp.profile_id).status is (
                    SlotStatus.signed
                ):
                    raise slot_signed()
            updated = _with_optional(state, inp.doc_id, inp.profile_id, inp.slot_id, inp.optional)
            # Пропуск при идущем маршруте снимет только новый раунд: маршрут уже прошёл этот шаг (13.3).
            returns_next_round = not inp.optional and skip is not None and held is not None
            if not inp.optional and skip is not None and held is None:
                updated = _without_skip(updated, inp.doc_id, inp.slot_id)
            changed = updated != state
            if changed:
                self._signature_repo.save_state(project.folder, updated)
        if changed:
            logger.info(
                "signature optional flag set",
                project_id=str(inp.project_id),
                doc_id=inp.doc_id,
                slot=inp.slot_id,
                profile_id=inp.profile_id,
                optional=inp.optional,
            )
            await self._record(inp, held)
        return SetSlotOptionalOutput(
            doc_id=inp.doc_id,
            slot_id=inp.slot_id,
            profile_id=inp.profile_id,
            optional=inp.optional,
            skipped=updated.skip_of(inp.doc_id, inp.slot_id, inp.profile_id) is not None,
            returns_next_round=returns_next_round,
        )

    async def _load(self, inp: SetSlotOptionalInput) -> tuple[Project, TemplateVersion, Document]:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )
        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(f"Документ {inp.doc_id!r} не найден", f"Document {inp.doc_id!r} not found")
            )
        return project, version, doc

    def _check_slot(
        self,
        project: Project,
        version: TemplateVersion,
        doc: Document,
        inp: SetSlotOptionalInput,
        routes: tuple[HeldRoute, ...],
        state: SignaturesState,
    ) -> None:
        """Слот ставится на документ точки или включён её маршрутом сверх точки, а пак не запрещает отметку.

        Снять уже стоящую отметку или пропуск можно и у слота, который маршрут больше не включает (маршрут отменён
        или снят с контроля): иначе пропуск слота сверх точки было бы не снять.
        """
        profile = SubmissionProfileService().get_profile(version, inp.profile_id)
        if profile is None:
            raise NotFoundError(
                localized_error(
                    f"Контрольная точка {inp.profile_id!r} не найдена", f"Checkpoint {inp.profile_id!r} not found"
                )
            )
        pair = DocSlot(inp.doc_id, inp.slot_id)
        on_point = any(
            p.doc.id == inp.doc_id and p.slot_id == inp.slot_id for p in profile_pairs(project, version, profile, None)
        )
        extra = any(r.profile_id == inp.profile_id and pair in r.pairs for r in routes)
        recorded = state.is_optional(inp.doc_id, inp.profile_id, inp.slot_id) or (
            state.skip_of(inp.doc_id, inp.slot_id, inp.profile_id) is not None
        )
        if not inp.optional and recorded:
            return
        runtime = self._slots.find_runtime_slot(project, version, inp.slot_id)
        if runtime is None or not (on_point or extra):
            raise unknown_slot()
        if inp.optional and runtime.required:
            raise optional_forbidden()

    async def _record(self, inp: SetSlotOptionalInput, held: HeldRoute | None) -> None:
        if self._audit is None:
            return
        details: dict[str, object] = {
            "doc_id": inp.doc_id,
            "slot_id": inp.slot_id,
            "profile_id": inp.profile_id,
            "optional": inp.optional,
        }
        if held is not None:
            details["route_id"] = str(held.route_id)
        await self._audit.record("signature.optional", project_id=inp.project_id, details=details)
