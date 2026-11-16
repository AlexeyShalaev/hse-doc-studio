"""Профили сдачи, пункты и порядок маршрута версии шаблона формой (docs/design/template-studio.md, 5.5-5.8, T13).

Модель читается из `version.yaml` версии, правка идёт под замком пространства с `If-Match` по ETag манифеста
(`PackFilesService.edit_yaml`), как у мест подписей (T9): выпущенная версия отвечает `version_released`, чужая
правка между чтением и записью `stale_file`. Невыполнимая правка (`SubmissionEditError`) это `submission_invalid`
с причиной по-английски, файл не меняется.

«Маршрут в этой комбинации» (5.6) считается тем же кодом, что маршрут проекта: точка (`build_point`), пресет
(`route_preset`) и порядок по умолчанию (`default_route`) на синтетическом проекте предпросмотра (набор данных и
переключатели 6.2). Модель версии та же, что у сборки предпросмотра: разбор в отдельном процессе и его кэш.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import SlotCondition, SubmissionProfile, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.invitations.entities import SUPERVISOR_PERSONAS
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.predicates import item_skipped, nda_enabled
from hse_doc_studio.core.pack_studio.paths import VERSION_MANIFEST, VersionRef
from hse_doc_studio.core.pack_studio.protocols import IPackSubmission
from hse_doc_studio.core.pack_studio.submission import (
    MAX_SUBMISSION_OPS,
    PairSource,
    ProfileRoute,
    RoutePair,
    RoutePerson,
    SkippedPair,
    SubmissionEditError,
    SubmissionOp,
    SubmissionRoutes,
    VersionSubmission,
    WhenCondition,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.plan import AUTHOR_PERSONA, slot_persona
from hse_doc_studio.core.signatures.route_order import default_route
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.team import is_doc_active, split_instance_id
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, version_ref
from hse_doc_studio.use_cases.pack_studio.synthetic_project import synthetic_core_project
from hse_doc_studio.use_cases.signing_route.point import RoutePoint, build_point
from hse_doc_studio.use_cases.signing_route.preset import route_preset


@dataclass(frozen=True)
class SubmissionView:
    """Профили версии: манифест (путь, ETag, почему только чтение) и модель."""

    ref: VersionRef
    path: str
    etag: str
    read_only: str | None
    submission: VersionSubmission


class PackSubmissionService:
    def __init__(self, files: PackFilesService, previews: PackPreviewService, editor: IPackSubmission) -> None:
        self._files = files
        self._previews = previews
        self._editor = editor

    async def get(self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str) -> SubmissionView:
        ref = version_ref(pack, template, version)
        path = _manifest(ref)
        found = await self._files.read(actor, workspace_id, path)
        submission = await asyncio.to_thread(self._describe, _text(found.content))
        return SubmissionView(ref, path, found.etag, found.read_only, submission)

    async def edit(  # noqa: PLR0913 — путь версии, правки и версия файла
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        ops: Sequence[SubmissionOp],
        if_match: str | None,
    ) -> SubmissionView:
        if not 0 < len(ops) <= MAX_SUBMISSION_OPS:
            raise PackStudioError(PackStudioErrorCode.submission_invalid, reason=f"1..{MAX_SUBMISSION_OPS} operations")
        ref = version_ref(pack, template, version)
        path = _manifest(ref)

        def edit(text: str) -> str:
            try:
                return self._editor.apply(text, ops)
            except SubmissionEditError as exc:
                raise PackStudioError(PackStudioErrorCode.submission_invalid, reason=str(exc)[:300]) from None
            except (TypeError, ValueError) as exc:
                raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None

        written = await self._files.edit_yaml(actor, workspace_id, path, edit, if_match)
        text = written.content or ""
        submission = await asyncio.to_thread(self._describe, text)
        return SubmissionView(ref, path, file_etag(text.encode("utf-8")), None, submission)

    async def routes(  # noqa: PLR0913 — путь версии, набор и комбинация
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        example: str | None,
        combination: Mapping[str, str] | None,
    ) -> SubmissionRoutes:
        """«Маршрут в этой комбинации» у каждого профиля версии (5.6)."""
        desc, chosen, combo, synthetic = await self._previews.synthetic(
            actor, workspace_id, pack, template, version, example, combination
        )
        project = synthetic_core_project(desc.pack_id, desc.template_id, desc.version, synthetic)
        profiles = desc.version.pack_submission.profiles if desc.version.pack_submission is not None else ()
        return SubmissionRoutes(
            example=chosen.id,
            combination=combo,
            profiles=tuple(profile_route(project, desc.version, profile) for profile in profiles),
        )

    def _describe(self, text: str) -> VersionSubmission:
        try:
            return self._editor.describe(text)
        except (TypeError, ValueError) as exc:
            raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None


def _when(condition: SlotCondition | None) -> WhenCondition | None:
    if condition is None:
        return None
    return WhenCondition(condition.person, condition.role.value if condition.role is not None else None)


def _person(project: Project, persona: str) -> RoutePerson:
    """Участник шага: роль и имя из синтетического проекта (автор по слагу, в одиночной работе первый)."""
    if persona in SUPERVISOR_PERSONAS:
        person = getattr(project, persona, None)
        return RoutePerson(persona, persona, person.name if person is not None else "")
    author = next((a for a in project.authors if a.slug == persona), None)
    if author is None and persona == AUTHOR_PERSONA and project.authors:
        author = project.authors[0]
    return RoutePerson(persona, AUTHOR_PERSONA, author.name if author is not None else "")


def _catalog_pair(point: RoutePoint, pair: DocSlot) -> tuple[str, str] | None:
    doc = point.documents.get(pair.doc_id)
    if doc is None:
        return None
    return doc.def_id, split_instance_id(pair.slot_id)[0]


def _items_off(project: Project, profile: SubmissionProfile) -> tuple[str, ...]:
    """Документы пунктов, которые в этой комбинации не сдаются: NDA, вид работы или документа в проекте нет."""
    present = {doc.def_id for doc in project.documents if is_doc_active(project, doc)}
    nda = nda_enabled(project.meta)
    kind = str(project.kind)
    off = (
        item.doc_id
        for item in profile.items
        if item_skipped(skip_if_nda=item.skip_if_nda, item_kinds=item.supported_kinds, kind=kind, nda=nda)
        or item.doc_id not in present
    )
    return tuple(dict.fromkeys(off))


def profile_route(project: Project, version: TemplateVersion, profile: SubmissionProfile) -> ProfileRoute:
    """Маршрут точки на проекте: те же точка, пресет и порядок, что у маршрута подписания проекта."""
    point = build_point(project, version, profile, ProjectTemplateService())
    preset = route_preset(point)
    optional = set(preset.optional) if preset is not None else set()
    extras = preset.extra_slots if preset is not None else ()
    pairs: dict[tuple[str, str, str], RoutePair] = {}
    for pair in point.required:
        key = _catalog_pair(point, pair)
        if key is not None:
            persona = slot_persona(pair.slot_id)
            pairs.setdefault((*key, persona), RoutePair(*key, persona, PairSource.point, optional=pair in optional))
    for item in extras:
        key = _catalog_pair(point, item.pair)
        if key is not None:
            persona = slot_persona(item.pair.slot_id)
            pairs.setdefault(
                (*key, persona),
                RoutePair(*key, persona, PairSource.preset, optional=item.pair in optional, when=_when(item.when)),
            )
    skipped = {
        key: SkippedPair(*key, _when(item.when))
        for item in (preset.skipped_by_condition if preset is not None else ())
        if (key := _catalog_pair(point, item.pair)) is not None
    }
    added = {(p.doc_id, p.slot_id) for p in pairs.values()}
    may_add = tuple(
        dict.fromkeys(
            key
            for pair in point.optional_pairs()
            if (key := _catalog_pair(point, pair)) is not None and key not in added and key not in skipped
        )
    )
    steps = preset.steps if preset is not None else default_route(version, profile, project)
    order_source = "profile" if profile.signing_route else "version" if version.signatures_config.route else "builtin"
    return ProfileRoute(
        id=profile.id,
        steps=tuple(tuple(_person(project, persona) for persona in step) for step in steps),
        pairs=tuple(pairs.values()),
        skipped=tuple(skipped.values()),
        may_add=may_add,
        items_off=_items_off(project, profile),
        order_source=order_source,
        preset=preset is not None,
    )


def _manifest(ref: VersionRef) -> str:
    return f"{ref.dir}/{VERSION_MANIFEST}"


def _text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise PackStudioError(PackStudioErrorCode.version_unreadable, reason="version.yaml is not UTF-8") from None
