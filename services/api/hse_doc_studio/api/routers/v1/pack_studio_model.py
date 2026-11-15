"""`/api/v1/pack-studio/.../model`: формы версии шаблона (docs/design/template-studio.md, 5.0, 5.2–5.3; T11 и T12).

`GET` отдаёт модель версии: манифест версии и `doc.yaml` документов как данные с ETag каждого файла, файлы
документов по языкам, где печатается каждое поле. `PATCH` применяет точечные правки YAML к одному манифесту
(`If-Match` по его ETag) и не пишет правку, после которой лоадер или схема пака найдут в файле новое
(`model_invalid`). `POST .../model/actions` делает операции на несколько файлов: переименование поля, новый и
удаляемый документ, перевод (`If-Match` по ETag `version.yaml`). Ответ всех трёх одна и та же модель.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Response

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_studio import (
    PackDocFile,
    PackDocLibraryItem,
    PackDocLibraryResponse,
    PackFieldUsage,
    PackModelActionRequest,
    PackModelDocument,
    PackModelFile,
    PackModelPatchRequest,
    PackVersionModelResponse,
    ReadOnlyReason,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.model import ModelAction, ModelActionKind, ModelFile
from hse_doc_studio.use_cases.pack_studio.files import YamlOp
from hse_doc_studio.use_cases.pack_studio.model import ModelView, PackModelService

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_MODEL = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/model"
_NO_STORE = {"Cache-Control": "no-store"}

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _file(file: ModelFile) -> PackModelFile:
    return PackModelFile(path=file.path, etag=file.etag, data=file.data)


def model_response(workspace_id: UUID, view: ModelView) -> PackVersionModelResponse:
    model = view.model
    read_only: ReadOnlyReason | None = "version_released" if view.read_only == "version_released" else None
    return PackVersionModelResponse(
        workspace_id=str(workspace_id),
        pack=view.ref.pack,
        template=view.ref.template,
        version=view.ref.version,
        read_only=read_only,
        manifest=_file(model.manifest),
        documents=[
            PackModelDocument(
                id=doc.id,
                manifest=_file(doc.manifest) if doc.manifest is not None else None,
                data=doc.data,
                files=[PackDocFile(path=f.path, bare=f.bare, lang=f.lang, size=f.size) for f in doc.files],
                references=list(doc.references),
            )
            for doc in model.documents
        ],
        usage=[
            PackFieldUsage(field=u.field, document=u.document, macros=list(u.macros), direct=u.direct, whole=u.whole)
            for u in model.usage
        ],
        checks=list(model.checks),
        problems=list(model.problems),
        changed=list(view.changed),
    )


def _headers(response: Response, view: ModelView) -> None:
    response.headers.update({"ETag": view.model.manifest.etag, **_NO_STORE})


@router.get(_MODEL, response_model=PackVersionModelResponse)
async def get_model(  # noqa: PLR0913 — путь версии
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    service: FromDishka[PackModelService],
    response: Response,
) -> PackVersionModelResponse:
    """Модель версии для форм: манифесты, документы и их файлы по языкам, где печатается поле."""
    view = await service.get(require_actor(), workspace_id, pack, template, version)
    _headers(response, view)
    return model_response(workspace_id, view)


@router.patch(_MODEL, response_model=PackVersionModelResponse)
async def patch_model(  # noqa: PLR0913 — путь версии, тело и версия файла
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackModelPatchRequest,
    service: FromDishka[PackModelService],
    response: Response,
    if_match: IfMatch = None,
) -> PackVersionModelResponse:
    """Точечные правки одного манифеста версии (весь набор или ничего); новая находка лоадера: `model_invalid`."""
    ops = [YamlOp(op=o.op, path=tuple(o.path), value=o.value, index=o.index, to=o.to) for o in body.ops]
    view = await service.patch(require_actor(), workspace_id, pack, template, version, body.file, ops, if_match)
    _headers(response, view)
    return model_response(workspace_id, view)


@router.post(f"{_MODEL}/actions", response_model=PackVersionModelResponse)
async def model_action(  # noqa: PLR0913 — путь версии, тело и версия манифеста
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackModelActionRequest,
    service: FromDishka[PackModelService],
    response: Response,
    if_match: IfMatch = None,
) -> PackVersionModelResponse:
    """Переименование поля, новый или удаляемый документ, перевод файлов документа."""
    action = ModelAction(
        kind=ModelActionKind(body.action),
        field=body.field,
        to=body.to,
        document=body.document,
        name=body.name,
        source=body.source,
        lang=body.lang,
        files=tuple(body.files),
    )
    view = await service.act(require_actor(), workspace_id, pack, template, version, action, if_match)
    _headers(response, view)
    return model_response(workspace_id, view)


@router.get("/pack-studio/workspaces/{workspace_id}/doc-library", response_model=PackDocLibraryResponse)
async def doc_library(workspace_id: UUID, service: FromDishka[PackModelService]) -> PackDocLibraryResponse:
    """Документы-заготовки пространства: последняя версия каждого шаблона."""
    found = await service.library(require_actor(), workspace_id)
    return PackDocLibraryResponse(
        documents=[
            PackDocLibraryItem(path=d.path, pack=d.pack, template=d.template, version=d.version, id=d.id, name=d.name)
            for d in found
        ]
    )
