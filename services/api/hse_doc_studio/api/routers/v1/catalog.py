from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.catalog import (
    DocumentDefinitionResponse,
    DocumentVariantResponse,
    MetaFieldResponse,
    MetaGroupResponse,
    PackResponse,
    SignatureSlotResponse,
    SubmissionDocItemResponse,
    SubmissionExtraItemResponse,
    SubmissionProfileResponse,
    TemplateInfoResponse,
    VersionDetailResponse,
    VersionListItemResponse,
)
from hse_doc_studio.core.catalog import (
    DocumentDefinition,
    MetaFieldDef,
    PackInfo,
    SignatureSlotDef,
    SubmissionProfile,
    TemplateInfo,
    TemplateVersion,
)
from hse_doc_studio.core.repositories import ITemplateRepository

router = APIRouter(route_class=DishkaRoute)


def _map_template_info(t: TemplateInfo) -> TemplateInfoResponse:
    return TemplateInfoResponse(
        id=t.id,
        name=t.name,
        short_name=t.short_name,
        icon=t.icon,
        accent_hue=t.accent_hue,
        default_version=t.default_version,
    )


def _map_pack(pack: PackInfo) -> PackResponse:
    return PackResponse(
        id=pack.id,
        name=pack.name,
        description=pack.description,
        maintainer=pack.maintainer,
        templates=[_map_template_info(t) for t in pack.templates],
    )


def _map_doc_def(doc: DocumentDefinition) -> DocumentDefinitionResponse:
    return DocumentDefinitionResponse(
        id=doc.id,
        name=doc.name,
        code=doc.code,
        required=doc.required,
        source_file=doc.source_file,
        output_file=doc.output_file,
        gost_ref=doc.gost_ref,
        supported_langs=list(doc.supported_langs),
        variants=[
            DocumentVariantResponse(
                id=v.id,
                label=v.label,
                source_file=v.source_file,
                output_file=v.output_file,
                supported_langs=list(v.supported_langs),
            )
            for v in doc.variants
        ],
        scope=doc.scope,
        supported_staffing=list(doc.supported_staffing),
        supported_kinds=list(doc.supported_kinds),
    )


def _map_meta_field(field: MetaFieldDef) -> MetaFieldResponse:
    return MetaFieldResponse(
        type=str(field.type),
        label=field.label,
        placeholder=field.placeholder,
        required_at=str(field.required_at),
        help=field.help,
        default=field.default,
        auto=str(field.auto) if field.auto is not None else None,
        options=list(field.options),
        group=field.group,
        scope=field.scope,
        supported_kinds=list(field.supported_kinds),
    )


def _map_slot(slot: SignatureSlotDef) -> SignatureSlotResponse:
    return SignatureSlotResponse(
        id=slot.id,
        label=slot.label,
        applies_to=list(slot.applies_to),
        default_placement={
            "page": slot.default_placement.page,
            "x_mm": slot.default_placement.x_mm,
            "y_mm": slot.default_placement.y_mm,
            "width_mm": slot.default_placement.width_mm,
        },
        per_author=slot.per_author,
    )


def _map_submission_profile(profile: SubmissionProfile) -> SubmissionProfileResponse:
    return SubmissionProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        items=[
            SubmissionDocItemResponse(
                doc_id=item.doc_id,
                signatures=list(item.signatures),
                skip_if_nda=item.skip_if_nda,
                supported_kinds=list(item.supported_kinds),
            )
            for item in profile.items
        ],
        extra_items=[
            SubmissionExtraItemResponse(
                source=extra.source,
                output_name=extra.output_name,
                format=extra.format,
                supported_kinds=list(extra.supported_kinds),
            )
            for extra in profile.extra_items
        ],
    )


def _map_version_detail(tv: TemplateVersion) -> VersionDetailResponse:
    return VersionDetailResponse(
        version=tv.version,
        status=str(tv.status),
        engine_config={
            "default": str(tv.engine_config.default),
            "allowed": [str(e) for e in tv.engine_config.allowed],
            "passes": tv.engine_config.passes,
        },
        documents=[_map_doc_def(d) for d in tv.documents],
        meta_fields={k: _map_meta_field(v) for k, v in tv.meta_fields.items()},
        meta_groups=[MetaGroupResponse(id=g.id, label=g.label, section=g.section) for g in tv.meta_groups],
        signatures={
            "slots": [_map_slot(s).model_dump() for s in tv.signatures_config.slots],
        },
        pack_submission={
            "profiles": [_map_submission_profile(p).model_dump() for p in tv.pack_submission.profiles],
        },
        supported_staffing=list(tv.supported_staffing),
    )


@router.get("/catalog/packs", response_model=list[PackResponse])
async def list_packs(
    template_repo: FromDishka[ITemplateRepository],
) -> list[PackResponse]:
    packs = template_repo.list_packs()
    return [_map_pack(p) for p in packs]


@router.get(
    "/catalog/packs/{pack_id}/templates/{template_id}/versions",
    response_model=list[VersionListItemResponse],
)
async def list_versions(
    pack_id: str,
    template_id: str,
    template_repo: FromDishka[ITemplateRepository],
) -> list[VersionListItemResponse]:
    version_strings = template_repo.list_versions(pack_id, template_id)
    if not version_strings:
        raise HTTPException(status_code=404, detail=f"Template {pack_id}/{template_id} not found")

    # Determine default version from pack info
    packs = template_repo.list_packs()
    pack = next((p for p in packs if p.id == pack_id), None)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Pack {pack_id} not found")
    template = next((t for t in pack.templates if t.id == template_id), None)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found in pack {pack_id}")

    default_version = template.default_version
    result: list[VersionListItemResponse] = []

    for ver_str in version_strings:
        tv = template_repo.get_version(pack_id, template_id, ver_str)
        if tv is None:
            continue
        result.append(
            VersionListItemResponse(
                version=tv.version,
                status=str(tv.status),
                released_at=tv.released_at.isoformat(),
                summary=tv.summary,
                is_default=(tv.version == default_version),
            )
        )

    return result


@router.get(
    "/catalog/packs/{pack_id}/templates/{template_id}/versions/{version}",
    response_model=VersionDetailResponse,
)
async def get_version(
    pack_id: str,
    template_id: str,
    version: str,
    template_repo: FromDishka[ITemplateRepository],
) -> VersionDetailResponse:
    tv = template_repo.get_version(pack_id, template_id, version)
    if tv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for {pack_id}/{template_id}",
        )
    return _map_version_detail(tv)
