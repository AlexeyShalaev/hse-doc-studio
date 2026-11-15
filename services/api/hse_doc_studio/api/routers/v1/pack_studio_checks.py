"""`/api/v1/pack-studio/.../checks`: файлы правил `checks/*.yaml` и `checks_version` формой (срез T14).

`GET` отдаёт файлы правил версии (шапка, правила по индексам YAML) и `checks_version` с ETag манифеста. `PATCH
.../checks/files/{name}` применяет правки файла правил точечными правками с `If-Match` по его ETag, `PUT
.../checks/config` пишет `checks_version` с `If-Match` по ETag `version.yaml`; ответ тот же, что у `GET`.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import yaml
from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Response

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_studio import ReadOnlyReason
from hse_doc_studio.api.schemas.pack_studio_checks import (
    PackCheckRule,
    PackChecksConfig,
    PackChecksConfigRequest,
    PackChecksFile,
    PackChecksHeader,
    PackChecksOp,
    PackChecksPatchRequest,
    PackChecksResponse,
    PackIndexedRule,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.enums import CheckEngine
from hse_doc_studio.core.pack_studio.checks_form import (
    STRUCTURAL_CHECKS,
    ChecksConfig,
    ChecksHeader,
    ChecksOp,
    ChecksOpKind,
    RuleEntry,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.use_cases.pack_studio.checks_form import ChecksView, PackChecksFormService

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_CHECKS = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/checks"
_NO_STORE = {"Cache-Control": "no-store"}
_PARAMS_NODES = 5000

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _read_only(value: str | None) -> ReadOnlyReason | None:
    if value is None:
        return None
    return "version_released" if value == "version_released" else "releases_read_only"


def _rule(entry: RuleEntry | None) -> PackCheckRule | None:
    if entry is None:
        return None
    return PackCheckRule.model_validate(
        {
            "id": entry.id,
            "title": dict(entry.title),
            "description": dict(entry.description),
            "category": entry.category,
            "applies_to": list(entry.applies_to) if entry.applies_to is not None else None,
            "default_severity": entry.default_severity,
            "engine": entry.engine,
            "params": dict(entry.params),
        }
    )


def _header(header: ChecksHeader) -> PackChecksHeader:
    return PackChecksHeader(label=dict(header.label), ref=dict(header.ref), source=dict(header.source), url=header.url)


def checks_response(workspace_id: UUID, view: ChecksView) -> PackChecksResponse:
    config = view.config
    return PackChecksResponse(
        workspace_id=str(workspace_id),
        pack=view.ref.pack,
        template=view.ref.template,
        version=view.ref.version,
        documents=list(view.documents),
        files=[
            PackChecksFile(
                path=f.path,
                name=f.name,
                etag=f.etag,
                read_only=_read_only(f.read_only),
                header=_header(f.view.header),
                rules=[
                    PackIndexedRule(
                        index=r.index, entry=_rule(r.entry), params_yaml=_params_text(r.entry), error=r.error
                    )
                    for r in f.view.rules
                ],
                error=f.view.error,
            )
            for f in view.files
        ],
        config=PackChecksConfig(
            path=config.path,
            etag=config.etag,
            read_only=_read_only(config.read_only),
            disabled_categories=list(config.config.disabled_categories),
            disabled=list(config.config.disabled),
            severity_override=dict(config.config.severity_override or {}),
        ),
        engines=[engine.value for engine in CheckEngine],
        structural_checks=list(STRUCTURAL_CHECKS),
    )


def _params_text(entry: RuleEntry | None) -> str | None:
    if entry is None:
        return None
    if not entry.params:
        return ""
    return yaml.safe_dump(dict(entry.params), allow_unicode=True, sort_keys=False, width=100)


def _count(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + sum(_count(v) for v in value.values())
    if isinstance(value, list):
        return 1 + sum(_count(v) for v in value)
    return 1


def _params(text: str) -> dict[str, Any]:
    """Параметры правила из текста YAML: только словарь, без якорей-бомб."""
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as exc:
        raise PackStudioError(PackStudioErrorCode.checks_invalid, reason=f"params: {exc}"[:300]) from None
    if data is None:
        data = {}
    if not isinstance(data, dict) or _count(data) > _PARAMS_NODES:
        raise PackStudioError(PackStudioErrorCode.checks_invalid, reason="params must be a mapping")
    return {str(k): v for k, v in data.items()}


def _op(body: PackChecksOp) -> ChecksOp:
    rule = body.rule
    entry: RuleEntry | None = None
    if rule is not None:
        params = _params(body.params_yaml) if body.params_yaml is not None else dict(rule.params)
        entry = RuleEntry(
            id=rule.id,
            title=rule.title,
            description=rule.description,
            category=rule.category,
            applies_to=tuple(rule.applies_to) if rule.applies_to is not None else None,
            default_severity=rule.default_severity,
            engine=rule.engine,
            params=params,
        )
    header = body.header
    return ChecksOp(
        op=ChecksOpKind(body.op),
        header=ChecksHeader(header.label, header.ref, header.source, header.url) if header is not None else None,
        index=body.index,
        to=body.to,
        rule=entry,
    )


@router.get(_CHECKS, response_model=PackChecksResponse)
async def get_checks(  # noqa: PLR0913 — путь версии
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    checks: FromDishka[PackChecksFormService],
    response: Response,
) -> PackChecksResponse:
    """Файлы правил версии и `checks_version` (5.7)."""
    view = await checks.get(require_actor(), workspace_id, pack, template, version)
    response.headers.update(_NO_STORE)
    return checks_response(workspace_id, view)


@router.patch(f"{_CHECKS}/files/{{name}}", response_model=PackChecksResponse)
async def patch_checks_file(  # noqa: PLR0913 — путь версии, файл, тело и версия файла
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    name: str,
    body: PackChecksPatchRequest,
    checks: FromDishka[PackChecksFormService],
    response: Response,
    if_match: IfMatch = None,
) -> PackChecksResponse:
    """Правки файла правил (весь набор или ничего); выпущенная версия: `version_released`."""
    view = await checks.edit_file(
        require_actor(), workspace_id, pack, template, version, name, [_op(op) for op in body.ops], if_match
    )
    response.headers.update(_NO_STORE)
    return checks_response(workspace_id, view)


@router.put(f"{_CHECKS}/config", response_model=PackChecksResponse)
async def put_checks_config(  # noqa: PLR0913 — путь версии, тело и версия файла
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackChecksConfigRequest,
    checks: FromDishka[PackChecksFormService],
    response: Response,
    if_match: IfMatch = None,
) -> PackChecksResponse:
    """`checks_version` версии: выключенные категории и правила, переопределение важности."""
    config = ChecksConfig(tuple(body.disabled_categories), tuple(body.disabled), dict(body.severity_override))
    view = await checks.edit_config(require_actor(), workspace_id, pack, template, version, config, if_match)
    response.headers.update(_NO_STORE)
    return checks_response(workspace_id, view)
