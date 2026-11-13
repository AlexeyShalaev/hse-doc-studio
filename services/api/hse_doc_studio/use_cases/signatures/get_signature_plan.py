"""План подписей проекта, профиля сдачи или документа: кто, каким способом, в каком статусе и чего не хватает."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.catalog import SubmissionProfile, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import ProjectStaffing, SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import (
    ProjectTemplateService,
    RuntimeSlot,
    SignatureSlotService,
    SubmissionProfileService,
    expand_slot_ids_for_doc,
)
from hse_doc_studio.core.signatures.plan import (
    DocFacts,
    DocPlan,
    PlanDate,
    PlanSlot,
    SignaturePlan,
    frozen_is_current,
    method_of,
    signer_for,
    slot_state,
)
from hse_doc_studio.core.signatures.ports import ISignerScope
from hse_doc_studio.core.signatures.stamps import (
    date_mark_text,
    legacy_stamps_digest,
    stamps_digest,
    stamps_for_doc,
)
from hse_doc_studio.core.team import is_doc_active
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures.signing_source import source_and_working


@dataclass
class GetSignaturePlanInput:
    project_id: UUID
    profile_id: str | None = None
    # Командный проект: чей пакет; без автора план объединяет пакеты всех авторов.
    author: str | None = None
    doc_id: str | None = None


@dataclass
class _Pair:
    doc: Document
    slot_id: str
    allowed: tuple[str, ...] = ()
    required_by: list[str] = field(default_factory=list)


class GetSignaturePlanUC:
    def __init__(  # noqa: PLR0913 — порты перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        signer_scope: ISignerScope | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._signer_scope = signer_scope
        self._slots = SignatureSlotService()
        self._profiles = SubmissionProfileService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSignaturePlanInput) -> SignaturePlan:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )
        state = self._signature_repo.get_state(project.folder)
        pairs = self._profile_pairs(project, version, inp) if inp.profile_id else self._project_pairs(project, version)
        if inp.doc_id is not None:
            pairs = [p for p in pairs if p.doc.id == inp.doc_id]
        personas = await self._signer_scope.personas(project) if self._signer_scope is not None else None
        return await build_plan(
            project, version, state, pairs_by_doc(pairs), self._template_service, inp.profile_id, personas
        )

    def _profile_pairs(self, project: Project, version: TemplateVersion, inp: GetSignaturePlanInput) -> list[_Pair]:
        profile = self._profiles.get_profile(version, inp.profile_id or "")
        if profile is None:
            raise NotFoundError(
                localized_error(
                    f"Контрольная точка {inp.profile_id!r} не найдена", f"Checkpoint {inp.profile_id!r} not found"
                )
            )
        return profile_pairs(project, version, profile, inp.author)

    def _project_pairs(self, project: Project, version: TemplateVersion) -> list[_Pair]:  # noqa: C901
        """Все пары, которые требует хоть одна точка, и все включённые размещения применимых слотов."""
        required = self._slots.required_by_profiles(project, version)
        docs = {d.id: d for d in project.documents}
        pairs: dict[tuple[str, str], _Pair] = {}
        for slot_id, by_doc in required.items():
            for doc_id, profile_ids in by_doc.items():
                if doc_id in docs:
                    pairs[(doc_id, slot_id)] = _Pair(docs[doc_id], slot_id, (), list(profile_ids))
        state = self._signature_repo.get_state(project.folder)
        runtime = {s.id: s for s in self._slots.runtime_slots(project, version)}
        for doc_id, placements in state.placements.items():
            doc = docs.get(doc_id)
            if doc is None or not is_doc_active(project, doc):
                continue
            for slot_id, placement in placements.items():
                slot = runtime.get(slot_id)
                if placement.enabled and slot is not None and self._slots.slot_applies_to_doc(slot, doc):
                    pairs.setdefault((doc_id, slot_id), _Pair(doc, slot_id))
        order = {d.id: i for i, d in enumerate(project.documents)}
        return sorted(pairs.values(), key=lambda p: (order.get(p.doc.id, 0), p.slot_id))


def profile_pairs(  # noqa: C901 — гейты пунктов профиля как у сборки пакета
    project: Project, version: TemplateVersion, profile: SubmissionProfile, author: str | None
) -> list[_Pair]:
    """Пары «документ, слот» профиля сдачи с теми же гейтами, что у сборки пакета."""
    slots = SignatureSlotService()
    team = project.staffing == ProjectStaffing.team
    slot_defs = {s.id: s for s in version.signatures_config.slots}
    runtime = {s.id: s for s in slots.runtime_slots(project, version)}
    authors: list[str | None] = [author] if author or not team else [a.slug for a in project.authors if a.slug]
    seen: dict[tuple[str, str], _Pair] = {}
    for item in profile.items:
        if item.skip_if_nda and bool(project.meta.get("nda")):
            continue
        if str(project.kind) not in item.supported_kinds:
            continue
        for slug in authors:
            for doc in _instances(project, item.doc_id, slug, team=team):
                for slot_id in expand_slot_ids_for_doc(item.signatures, slot_defs, project, doc, team=team):
                    slot = runtime.get(slot_id)
                    if slot is None or not slots.slot_applies_to_doc(slot, doc):
                        continue
                    pair = seen.setdefault((doc.id, slot_id), _Pair(doc, slot_id, item.allowed_methods(slot_id)))
                    if profile.id not in pair.required_by:
                        pair.required_by.append(profile.id)
    return list(seen.values())


def _instances(project: Project, def_id: str, author: str | None, *, team: bool) -> Iterable[Document]:
    for doc in project.documents:
        if doc.def_id != def_id or not is_doc_active(project, doc):
            continue
        if team and doc.owner is not None and doc.owner != author:
            continue
        yield doc


def pairs_by_doc(pairs: Iterable[_Pair]) -> dict[str, list[_Pair]]:
    grouped: dict[str, list[_Pair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.doc.id, []).append(pair)
    return grouped


async def doc_facts(
    project: Project, version: TemplateVersion, doc: Document, state: SignaturesState, ts: ProjectTemplateService
) -> DocFacts:
    """Факты документа для плана: источник подписи (версия на подписи или сборка), рабочая сборка, видимый слой."""
    folder = project.folder
    compiled: Path | None = None
    try:
        output_file = ts.resolve_signing_output(project, doc, version)
        compiled = folder / output_file if output_file else None
    except (NotFoundError, ValueError):
        compiled = None
    source, working = await source_and_working(folder, compiled, state, doc.id)
    stamps = stamps_for_doc(state, doc.id, folder, str(project.lang))
    return DocFacts(
        compiled_sha256=source.sha256,
        marks_digest=stamps_digest(stamps, folder),
        png_exists=lambda rel: (folder / rel).is_file(),
        legacy_marks_digest=legacy_stamps_digest(stamps),
        working_sha256=working,
    )


def plan_dates(state: SignaturesState, doc_id: str, slot_id: str, lang: str) -> tuple[PlanDate, ...]:
    """Метки даты слота документа для плана (signing-route.md, 14.7): что каждая напечатает сейчас."""
    placement = state.placements.get(doc_id, {}).get(slot_id)
    if placement is None:
        return ()
    return tuple(
        PlanDate(page=mark.page, format=mark.format, text=date_mark_text(state, doc_id, slot_id, mark, lang))
        for mark in placement.dates
    )


def pair_optional(
    state: SignaturesState, doc_id: str, slot_id: str, profile_id: str | None, required_by: Iterable[str]
) -> bool:
    """Подпись необязательна (signing-route.md, 13.3): на точке `profile_id`, а в плане проекта на каждой точке, которая
    её требует; слот, который не требует ни одна точка, необязателен, если его отметили хоть на одной."""
    if profile_id is not None:
        return state.is_optional(doc_id, profile_id, slot_id)
    points = list(required_by)
    if points:
        return all(state.is_optional(doc_id, point, slot_id) for point in points)
    return any(slot_id in slots for slots in state.optional.get(doc_id, {}).values())


async def build_plan(  # noqa: PLR0913 — входы расчёта
    project: Project,
    version: TemplateVersion,
    state: SignaturesState,
    grouped: dict[str, list[_Pair]],
    ts: ProjectTemplateService,
    profile_id: str | None,
    personas: frozenset[str] | None,
) -> SignaturePlan:
    runtime: dict[str, RuntimeSlot] = {s.id: s for s in SignatureSlotService().runtime_slots(project, version)}
    docs: list[DocPlan] = []
    for doc_id, pairs in grouped.items():
        doc = pairs[0].doc
        facts = await doc_facts(project, version, doc, state, ts)
        # Пропущенная пара не криптослот документа (signing-route.md, 13.3, инвариант 6).
        uses_frozen = any(
            method_of(slot.sign_mode if (slot := state.slots.get(p.slot_id)) else SignMode.image).value != "image"
            for p in pairs
            if state.skip_of(doc_id, p.slot_id, profile_id) is None
        )
        frozen = state.frozen.get(doc_id)
        pinned = state.pinned.get(doc_id)
        slots = tuple(
            PlanSlot(
                doc_id=doc_id,
                slot_id=p.slot_id,
                label=dict(runtime[p.slot_id].label) if p.slot_id in runtime else {"ru": p.slot_id},
                signer=(signer := signer_for(project, p.slot_id)),
                mode=slot.sign_mode if (slot := state.slots.get(p.slot_id)) else SignMode.image,
                state=slot_state(
                    state, doc_id, p.slot_id, facts, allowed=p.allowed, uses_frozen=uses_frozen, profile_id=profile_id
                ),
                allowed_methods=p.allowed,
                required_by=tuple(p.required_by),
                is_mine=personas is not None and signer.persona in personas,
                pinned=pinned is not None,
                optional=pair_optional(state, doc_id, p.slot_id, profile_id, p.required_by),
                skipped=state.skip_of(doc_id, p.slot_id, profile_id),
                dates=plan_dates(state, doc_id, p.slot_id, str(project.lang)),
                signed_at=placement.signed_at
                if (placement := state.placements.get(doc_id, {}).get(p.slot_id)) is not None
                else None,
            )
            for p in pairs
        )
        docs.append(
            DocPlan(
                doc_id=doc_id,
                built=facts.compiled_sha256 is not None,
                frozen=frozen,
                frozen_outdated=frozen_is_current(frozen, facts) if frozen is not None else None,
                slots=slots,
                pinned=pinned,
                working_differs=facts.working_differs,
            )
        )
    return SignaturePlan(docs=tuple(docs), profile_id=profile_id, personas=personas)
