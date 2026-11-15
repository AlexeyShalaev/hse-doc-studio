"""Ответы «Каталогов паков» из сценария (`use_cases/pack_catalog`) в схемы `api/schemas/pack_catalog.py`."""

from __future__ import annotations

from hse_doc_studio.api.schemas.pack_catalog import (
    AccessName,
    CatalogApplyResponse,
    CatalogCheckResponse,
    CatalogEventResponse,
    CatalogLimitsResponse,
    CatalogOverviewResponse,
    CatalogPackResponse,
    CatalogSourceErrorResponse,
    CatalogSourceResponse,
    CatalogVersionResponse,
    PlannedPackResponse,
    PlannedVersionResponse,
)
from hse_doc_studio.core.pack_catalog.entities import CatalogEvent, CatalogSource
from hse_doc_studio.core.pack_catalog.plan import CatalogPlan
from hse_doc_studio.core.pack_catalog.protocols import StageLimits
from hse_doc_studio.use_cases.pack_catalog.service import (
    ApplyView,
    CatalogOverview,
    CatalogPackView,
    CheckView,
    SourceView,
)


def _access(source: CatalogSource) -> AccessName:
    if source.service_access_id is not None:
        return "service"
    return "personal" if source.credential_id is not None else "none"


def pack_response(view: CatalogPackView) -> CatalogPackResponse:
    return CatalogPackResponse(
        id=view.id,
        name=dict(view.name),
        origin="subscribed" if view.origin_kind == "subscribed" else "builtin",
        source_id=view.source_id,
        listed=view.listed,
        replaces_builtin=view.replaces_builtin,
        versions=[
            CatalogVersionResponse(template=v.template, version=v.version, listed=v.listed) for v in view.versions
        ],
    )


def source_response(
    source: CatalogSource, *, busy: bool = False, packs: tuple[CatalogPackView, ...] = ()
) -> CatalogSourceResponse:
    return CatalogSourceResponse(
        id=str(source.id),
        kind=source.kind.value,
        label=source.label,
        enabled=source.enabled,
        replace_builtin=source.replace_builtin,
        track=source.track,
        packs_path=source.packs_path,
        url=source.url,
        ref=source.ref,
        access=_access(source),
        credential_id=None if source.credential_id is None else str(source.credential_id),
        service_access_id=None if source.service_access_id is None else str(source.service_access_id),
        insecure_http=source.insecure_http,
        archive_name=source.archive_name,
        archive_digest=source.archive_digest,
        folder=source.folder,
        workspace_id=None if source.workspace_id is None else str(source.workspace_id),
        applied_revision=source.applied_revision,
        applied_at=source.applied_at,
        checked_revision=source.checked_revision,
        checked_at=source.checked_at,
        check_ok=source.check_ok,
        pending_versions=source.pending_versions,
        error=None
        if source.error is None
        else CatalogSourceErrorResponse(code=source.error.code, detail=source.error.detail),
        busy=busy,
        created_at=source.created_at,
        updated_at=source.updated_at,
        created_by=source.created_by,
        packs=[pack_response(p) for p in packs],
    )


def source_view_response(view: SourceView) -> CatalogSourceResponse:
    return source_response(view.source, busy=view.busy, packs=view.packs)


def overview_response(view: CatalogOverview, limits: StageLimits) -> CatalogOverviewResponse:
    return CatalogOverviewResponse(
        revision=view.revision,
        sources=[source_view_response(s) for s in view.sources],
        packs=[pack_response(p) for p in view.packs],
        limits=CatalogLimitsResponse(
            max_archive_bytes=limits.max_archive_bytes, max_files=limits.max_files, max_bytes=limits.max_bytes
        ),
    )


def _planned(plan: CatalogPlan) -> list[PlannedPackResponse]:
    return [
        PlannedPackResponse(
            id=pack.id,
            name=dict(pack.name),
            conflict=None if pack.conflict is None else pack.conflict.value,
            conflict_with=pack.conflict_with,
            replaces_builtin=pack.replaces_builtin,
            problems=list(pack.problems),
            versions=[
                PlannedVersionResponse(
                    template=v.template,
                    version=v.version,
                    verdict=v.verdict.value,
                    digest=v.digest,
                    kind=v.kind,
                    min_studio=v.min_studio,
                    errors=list(v.errors),
                    warnings=list(v.warnings),
                )
                for v in pack.versions
            ],
        )
        for pack in plan.packs
    ]


def check_response(view: CheckView, source: SourceView | None = None) -> CatalogCheckResponse:
    return CatalogCheckResponse(
        source=source_view_response(source) if source is not None else source_response(view.source),
        revision=view.plan.revision,
        ok=view.plan.ok,
        blockers=[b.value for b in view.plan.blockers],
        new_count=view.plan.new_count,
        problems=list(view.plan.problems),
        packs=_planned(view.plan),
    )


def apply_response(view: ApplyView, source: SourceView | None = None) -> CatalogApplyResponse:
    return CatalogApplyResponse(
        source=source_view_response(source) if source is not None else source_response(view.source),
        revision=view.plan.revision,
        added=list(view.added),
        catalog_revision=view.catalog_revision,
    )


def event_response(event: CatalogEvent) -> CatalogEventResponse:
    return CatalogEventResponse(
        id=str(event.id),
        action=event.action.value,
        at=event.at,
        ok=event.ok,
        actor_id=event.actor_id,
        revision=event.revision,
        summary=dict(event.summary),
    )
