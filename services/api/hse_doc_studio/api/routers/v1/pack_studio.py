"""`/api/v1/pack-studio/*`: Студия шаблонов, срез T5 (docs/design/template-studio.md, разделы 4 и 12).

Гард раздела (`pack_studio_guard`) стоит на всех маршрутах рабочих пространств: раздел выключен (404
`pack_studio_disabled`), токен без области `packs` (403 `pack_scope_required`), нет права «Автор шаблонов» (403
`pack_studio_forbidden`). Состояние раздела (`/pack-studio/section`) открыто любому вошедшему: по нему интерфейс
решает, показывать ли раздел и переключатель в Настройках.

Файлы адресуются путём от папки паков пространства:
`files/hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`.

Предпросмотр (срез T7): `versions/{pack}/{template}/{version}/preview` отдаёт документы, переключатели и наборы данных
(GET) и запускает сборку (POST); ход сборки, PDF, журнал и якоря мест подписей по `previews/{build_id}`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.files import _content_type_for
from hse_doc_studio.api.schemas.pack_studio import (
    CreatePackWorkspaceRequest,
    PackBranchRequest,
    PackCheckFinding,
    PackCheckSummary,
    PackCiCheck,
    PackCiResponse,
    PackCommitRequest,
    PackCommitResponse,
    PackDiagnosticResponse,
    PackDiffResponse,
    PackEditorHintsResponse,
    PackFileChange,
    PackFileVersionResponse,
    PackGitResponse,
    PackLintRequest,
    PackLintResponse,
    PackMacroHintResponse,
    PackMetaFieldHintResponse,
    PackPreviewBuildResponse,
    PackPreviewDocument,
    PackPreviewErrorBody,
    PackPreviewExample,
    PackPreviewOptionsResponse,
    PackPreviewStartResponse,
    PackPreviewSwitch,
    PackProposeRequest,
    PackProposeResponse,
    PackPullRequest,
    PackStartOverRequest,
    PackStudioSectionResponse,
    PackTreeFile,
    PackTreePack,
    PackTreeResponse,
    PackTreeTemplate,
    PackTreeVersion,
    PackVersionClass,
    PackWorkspaceErrorBody,
    PackWorkspaceResponse,
    PackYamlPatchRequest,
    PackYamlPatchResponse,
    ReadOnlyReason,
    StartPackPreviewRequest,
    UpdatePackStudioSectionRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.entities import (
    DiagnosticSeverity,
    PackEditorHints,
    PackLintReport,
    PackTree,
    WorkspaceKind,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.preview import PreviewBuild
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess, SectionView
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService, YamlOp
from hse_doc_studio.use_cases.pack_studio.git import ForkChoice, GitView, PackGitService, ProposeInput
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewOptions, StartPreviewInput
from hse_doc_studio.use_cases.pack_studio.workspaces import (
    CreateWorkspaceInput,
    PackWorkspaceService,
    WorkspaceView,
)

_NO_STORE = {"Cache-Control": "no-store"}
READ_ONLY_HEADER = "X-Pack-Read-Only"


async def pack_studio_guard(request: Request) -> None:
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    access = await container.get(PackStudioAccess)
    await access.require(require_actor())


section_router = APIRouter(route_class=SafeDishkaRoute)
router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def section_response(view: SectionView) -> PackStudioSectionResponse:
    return PackStudioSectionResponse(
        enabled=view.enabled,
        locked=view.locked,
        allowed=view.allowed,
        has_right=view.has_right,
        standalone=view.standalone,
    )


def workspace_response(view: WorkspaceView) -> PackWorkspaceResponse:
    ws = view.workspace
    return PackWorkspaceResponse(
        id=str(ws.id),
        kind=ws.kind.value,
        label=ws.label,
        state=ws.state.value,
        busy=view.busy,
        packs_path=ws.packs_path,
        url=ws.remote_url,
        credential_id=None if ws.credential_id is None else str(ws.credential_id),
        service_access=ws.service_access_id is not None,
        insecure_http=ws.insecure_http,
        folder=view.folder_display,
        base_branch=ws.base_branch,
        base_sha=ws.base_sha,
        fetched_at=ws.fetched_at,
        work_branch=ws.work_branch,
        pr_url=ws.pr_url,
        pr_number=ws.pr_number,
        ci_status=ws.ci_status,
        fork_url=ws.fork_url,
        pushed_sha=ws.pushed_sha,
        error=None if ws.error is None else PackWorkspaceErrorBody(code=ws.error.code, detail=ws.error.detail),
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


def tree_response(workspace_id: UUID, base_sha: str | None, tree: PackTree) -> PackTreeResponse:
    return PackTreeResponse(
        workspace_id=str(workspace_id),
        base_sha=base_sha,
        packs=[
            PackTreePack(
                id=pack.id,
                path=pack.path,
                name=dict(pack.name) if pack.name else None,
                templates=[
                    PackTreeTemplate(
                        id=template.id,
                        path=template.path,
                        name=dict(template.name) if template.name else None,
                        default_version=template.default_version,
                        versions=[
                            PackTreeVersion(
                                version=v.version,
                                path=v.path,
                                status=v.status,
                                released=v.released,
                                modified=v.modified,
                            )
                            for v in template.versions
                        ],
                    )
                    for template in pack.templates
                ],
            )
            for pack in tree.packs
        ],
        files=[
            PackTreeFile(path=f.path, is_dir=f.is_dir, size=f.size, read_only=_reason(f.read_only)) for f in tree.files
        ],
        truncated=tree.truncated,
    )


def lint_response(report: PackLintReport) -> PackLintResponse:
    findings = [
        PackDiagnosticResponse(
            severity=f.severity.value,
            check=f.check.value,
            message=f.message,
            path=f.path,
            line=f.line,
            pointer=f.pointer,
        )
        for f in report.findings
    ]
    return PackLintResponse(
        scope=report.scope.value,
        target=report.target,
        released=report.released,
        errors=sum(1 for f in report.findings if f.severity is DiagnosticSeverity.error),
        warnings=sum(1 for f in report.findings if f.severity is DiagnosticSeverity.warning),
        findings=findings,
    )


def hints_response(hints: PackEditorHints) -> PackEditorHintsResponse:
    return PackEditorHintsResponse(
        version=hints.version,
        meta_fields=[
            PackMetaFieldHintResponse(key=f.key, type=f.type, label=dict(f.label) if f.label else None, group=f.group)
            for f in hints.meta_fields
        ],
        macros=[PackMacroHintResponse(name=m.name, keys=list(m.keys), source=m.source) for m in hints.macros],
    )


def _reason(value: str | None) -> ReadOnlyReason | None:
    if value == "version_released":
        return "version_released"
    if value == "releases_read_only":
        return "releases_read_only"
    return None


# ── раздел ──────────────────────────────────────────────────────────────────


@section_router.get("/pack-studio/section", response_model=PackStudioSectionResponse)
async def get_section(access: FromDishka[PackStudioAccess], response: Response) -> PackStudioSectionResponse:
    response.headers.update(_NO_STORE)
    return section_response(await access.view(require_actor()))


@section_router.put("/pack-studio/section", response_model=PackStudioSectionResponse)
async def put_section(
    body: UpdatePackStudioSectionRequest, access: FromDishka[PackStudioAccess]
) -> PackStudioSectionResponse:
    """Переключатель «Инструменты автора шаблонов» локальной Студии; на сервере раздел включает админ."""
    return section_response(await access.set_enabled(require_actor(), body.enabled))


# ── рабочие пространства ────────────────────────────────────────────────────


@router.get("/pack-studio/workspaces", response_model=list[PackWorkspaceResponse])
async def list_workspaces(service: FromDishka[PackWorkspaceService]) -> list[PackWorkspaceResponse]:
    return [workspace_response(view) for view in await service.list(require_actor())]


@router.post("/pack-studio/workspaces", status_code=201, response_model=PackWorkspaceResponse)
async def create_workspace(
    body: CreatePackWorkspaceRequest, service: FromDishka[PackWorkspaceService], response: Response
) -> PackWorkspaceResponse:
    """Папка готова сразу (201). Пространство над git отвечает 202 в состоянии `cloning`: клон идёт в фоне."""
    view = await service.create(
        require_actor(),
        CreateWorkspaceInput(
            kind=WorkspaceKind(body.kind),
            label=body.label,
            url=body.url,
            credential_id=body.credential_id,
            service_access=body.service_access,
            insecure_http=body.insecure_http,
            base_branch=body.base_branch,
            folder=body.folder,
            packs_path=body.packs_path,
        ),
    )
    if view.workspace.kind is WorkspaceKind.git:
        response.status_code = 202
    return workspace_response(view)


@router.get("/pack-studio/workspaces/{workspace_id}", response_model=PackWorkspaceResponse)
async def get_workspace(
    workspace_id: UUID, service: FromDishka[PackWorkspaceService], response: Response
) -> PackWorkspaceResponse:
    response.headers.update(_NO_STORE)
    return workspace_response(await service.get(require_actor(), workspace_id))


@router.delete("/pack-studio/workspaces/{workspace_id}", status_code=204, response_model=None)
async def delete_workspace(workspace_id: UUID, service: FromDishka[PackWorkspaceService]) -> None:
    await service.delete(require_actor(), workspace_id)


@router.post("/pack-studio/workspaces/{workspace_id}/refresh", status_code=202, response_model=PackWorkspaceResponse)
async def refresh_workspace(workspace_id: UUID, service: FromDishka[PackWorkspaceService]) -> PackWorkspaceResponse:
    """Выборка базовой ветки и пересчёт выпущенных версий; у неудачного или прерванного клона клон заново."""
    return workspace_response(await service.refresh(require_actor(), workspace_id))


@router.get("/pack-studio/workspaces/{workspace_id}/tree", response_model=PackTreeResponse)
async def get_tree(workspace_id: UUID, files: FromDishka[PackFilesService], response: Response) -> PackTreeResponse:
    response.headers.update(_NO_STORE)
    view = await files.tree(require_actor(), workspace_id)
    return tree_response(workspace_id, view.workspace.base_sha, view.tree)


# ── проверки и подсказки редактора (срез T8) ────────────────────────────────


@router.post("/pack-studio/workspaces/{workspace_id}/lint", response_model=PackLintResponse)
async def lint_path(
    workspace_id: UUID, body: PackLintRequest, insight: FromDishka[PackInsightService]
) -> PackLintResponse:
    """Файл версии: `pack_lint` версии и схемы её манифестов; манифест вне версии: схема; прочее: ничего.

    Находки разложены по файлам и строкам для редактора и панели «Проблемы» (template-studio.md, 4.4, 5.0).
    """
    return lint_response(await insight.lint(require_actor(), workspace_id, body.path))


@router.get("/pack-studio/workspaces/{workspace_id}/hints", response_model=PackEditorHintsResponse)
async def editor_hints(
    workspace_id: UUID, path: str, insight: FromDishka[PackInsightService], response: Response
) -> PackEditorHintsResponse:
    """Автодополнение `.j2` и `.tex` (5.4): поля анкеты версии файла и макросы `\\hse...` её динамических инклудов."""
    response.headers.update(_NO_STORE)
    return hints_response(await insight.hints(require_actor(), workspace_id, path))


# ── файлы ───────────────────────────────────────────────────────────────────


@router.get("/pack-studio/workspaces/{workspace_id}/files/{path:path}")
async def read_file(workspace_id: UUID, path: str, files: FromDishka[PackFilesService]) -> Response:
    """Содержимое с `ETag`; `X-Pack-Read-Only: version_released | releases_read_only`, если файл менять нельзя."""
    found = await files.read(require_actor(), workspace_id, path)
    headers = {"ETag": found.etag, **_NO_STORE}
    if found.read_only is not None:
        headers[READ_ONLY_HEADER] = found.read_only
    return Response(content=found.content, media_type=_content_type_for(found.path), headers=headers)


@router.put("/pack-studio/workspaces/{workspace_id}/files/{path:path}", response_model=PackFileVersionResponse)
async def write_file(
    workspace_id: UUID,
    path: str,
    request: Request,
    files: FromDishka[PackFilesService],
    response: Response,
    if_match: IfMatch = None,
) -> PackFileVersionResponse:
    """Файл целиком (тело запроса как есть). `If-Match` с ETag: запись только поверх той же версии."""
    content = await _body(request, files)
    written = await files.write(require_actor(), workspace_id, path, content, if_match)
    response.headers["ETag"] = written.etag
    return PackFileVersionResponse(path=written.path, etag=written.etag, size=written.size)


@router.patch("/pack-studio/workspaces/{workspace_id}/files/{path:path}", response_model=PackYamlPatchResponse)
async def patch_yaml(
    workspace_id: UUID,
    path: str,
    body: PackYamlPatchRequest,
    files: FromDishka[PackFilesService],
    response: Response,
    if_match: IfMatch = None,
) -> PackYamlPatchResponse:
    """Точечные правки YAML по пути узла (D11): остальной текст байт в байт; весь набор или ничего."""
    ops = [YamlOp(op=o.op, path=tuple(o.path), value=o.value, index=o.index, to=o.to) for o in body.ops]
    written = await files.patch_yaml(require_actor(), workspace_id, path, ops, if_match)
    response.headers["ETag"] = written.etag
    return PackYamlPatchResponse(path=written.path, etag=written.etag, size=written.size, content=written.content or "")


@router.delete("/pack-studio/workspaces/{workspace_id}/files/{path:path}", status_code=204, response_model=None)
async def delete_file(
    workspace_id: UUID, path: str, files: FromDishka[PackFilesService], if_match: IfMatch = None
) -> None:
    """Файл (с `If-Match` по желанию) или папка целиком; выпущенные версии и реестры выпусков не удаляются."""
    await files.delete(require_actor(), workspace_id, path, if_match)


async def _body(request: Request, files: PackFilesService) -> bytes:
    """Тело не длиннее предела записи: лишнее не читается в память."""
    limit = files.max_file_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise PackStudioError(PackStudioErrorCode.file_too_large, limit=limit)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise PackStudioError(PackStudioErrorCode.file_too_large, limit=limit)
        chunks.append(chunk)
    return b"".join(chunks)


# ── git: ветка, коммит, предложение, проверки (срез T6) ─────────────────────


def git_response(view: GitView) -> PackGitResponse:
    st = view.status
    return PackGitResponse(
        workspace=workspace_response(WorkspaceView(workspace=view.workspace, busy=False)),
        provider=view.provider.value,
        head_sha=st.head_sha,
        branch=st.branch,
        base_branch=view.workspace.base_branch,
        uncommitted=[PackFileChange(path=c.path, status=c.status.value) for c in st.uncommitted],
        dirty=st.dirty,
        changed=[PackFileChange(path=c.path, status=c.status.value) for c in st.changed],
        ahead=st.ahead,
        behind=st.behind,
        compare_url=view.compare_url,
    )


@router.get("/pack-studio/workspaces/{workspace_id}/git", response_model=PackGitResponse)
async def get_git(workspace_id: UUID, git: FromDishka[PackGitService], response: Response) -> PackGitResponse:
    response.headers.update(_NO_STORE)
    return git_response(await git.view(require_actor(), workspace_id))


@router.get("/pack-studio/workspaces/{workspace_id}/git/diff", response_model=PackDiffResponse)
async def get_git_diff(workspace_id: UUID, git: FromDishka[PackGitService], response: Response) -> PackDiffResponse:
    """Единый diff от базовой ветки: коммиты рабочей ветки и правки на диске (показ перед «Предложить»)."""
    response.headers.update(_NO_STORE)
    text, truncated = await git.diff(require_actor(), workspace_id)
    return PackDiffResponse(diff=text, truncated=truncated)


@router.post("/pack-studio/workspaces/{workspace_id}/git/branch", response_model=PackGitResponse)
async def switch_branch(
    workspace_id: UUID, body: PackBranchRequest, git: FromDishka[PackGitService]
) -> PackGitResponse:
    """Создать рабочую ветку (правки остаются) или перейти на свою прежнюю, локальную или с сервера (дерево чистое)."""
    return git_response(await git.switch(require_actor(), workspace_id, body.name))


@router.post("/pack-studio/workspaces/{workspace_id}/git/commit", response_model=PackCommitResponse)
async def commit(workspace_id: UUID, body: PackCommitRequest, git: FromDishka[PackGitService]) -> PackCommitResponse:
    """«Сохранить версию»: коммит правок от профиля человека; без ветки она создаётся."""
    view = await git.commit(require_actor(), workspace_id, body.message)
    return PackCommitResponse(git=git_response(view.git), sha=view.sha, committed=view.committed)


@router.post("/pack-studio/workspaces/{workspace_id}/git/propose", response_model=PackProposeResponse)
async def propose(workspace_id: UUID, body: PackProposeRequest, git: FromDishka[PackGitService]) -> PackProposeResponse:
    """«Предложить изменения»: коммит, проверки пака, push ветки, PR GitHub или MR GitLab (4.3)."""
    fork = ForkChoice(url=body.fork.url, create=body.fork.create) if body.fork is not None else None
    view = await git.propose(
        require_actor(),
        workspace_id,
        ProposeInput(title=body.title, description=body.description, message=body.message, fork=fork),
    )
    pull = view.pull_request
    return PackProposeResponse(
        git=git_response(view.git),
        pushed_sha=view.pushed_sha,
        pushed_to=view.pushed_to,
        pull_request=PackPullRequest(number=pull.number, url=pull.url, created=pull.created) if pull else None,
        compare_url=view.compare_url,
        pr_error=(
            PackWorkspaceErrorBody(code=view.pr_error.code.value, detail=view.pr_error.detail)
            if view.pr_error is not None
            else None
        ),
        checks=PackCheckSummary(
            errors=view.report.errors,
            warnings=view.report.warnings,
            findings=[
                PackCheckFinding(
                    severity="error" if f.severity == "error" else "warning",
                    check=f.check,
                    path=f.path,
                    message=f.message,
                )
                for f in view.report.findings
            ],
            classes=[
                PackVersionClass(
                    path=c.path,
                    base=c.base,
                    minimum=c.minimum,
                    suggested=c.suggested,
                    by_number=c.by_number,
                    headline=dict(c.headline),
                )
                for c in view.report.classes
            ],
        ),
    )


@router.get("/pack-studio/workspaces/{workspace_id}/git/checks", response_model=PackCiResponse)
async def get_checks(workspace_id: UUID, git: FromDishka[PackGitService], response: Response) -> PackCiResponse:
    """Статус проверок хостинга по отправленной вершине (4.4); опрос раз в 30 с, пока `pending`."""
    response.headers.update(_NO_STORE)
    report = await git.checks(require_actor(), workspace_id)
    return PackCiResponse(
        state=report.state.value,
        sha=report.sha,
        checks=[PackCiCheck(name=c.name, state=c.state.value, url=c.url, summary=c.summary) for c in report.checks],
        available=report.available,
        reason=report.reason,
        web_url=report.web_url,
    )


@router.post("/pack-studio/workspaces/{workspace_id}/git/merge-base", response_model=PackGitResponse)
async def merge_base(workspace_id: UUID, git: FromDishka[PackGitService]) -> PackGitResponse:
    """Выборка базы и слияние её в рабочую ветку; конфликт отменяет слияние (`merge_conflict` со списком файлов)."""
    return git_response(await git.merge_base(require_actor(), workspace_id))


@router.post("/pack-studio/workspaces/{workspace_id}/git/start-over", response_model=PackGitResponse)
async def start_over(
    workspace_id: UUID, body: PackStartOverRequest, git: FromDishka[PackGitService]
) -> PackGitResponse:
    """«Начать заново от базовой ветки» после слияния PR: дерево на свежую базу, ветка и PR забываются."""
    return git_response(await git.start_over(require_actor(), workspace_id, discard=body.discard))


# ── предпросмотр ────────────────────────────────────────────────────────────

_PREVIEW = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/preview"
_BUILD = "/pack-studio/workspaces/{workspace_id}/previews/{build_id}"


def preview_options_response(
    workspace_id: UUID, pack: str, template: str, version: str, options: PreviewOptions
) -> PackPreviewOptionsResponse:
    return PackPreviewOptionsResponse(
        workspace_id=str(workspace_id),
        pack=pack,
        template=template,
        version=version,
        pack_id=options.pack_id,
        template_id=options.template_id,
        version_id=options.version_id,
        documents=[
            PackPreviewDocument(
                id=doc.id, name=dict(doc.name), kinds=list(doc.supported_kinds), staffing=list(doc.supported_staffing)
            )
            for doc in options.documents
        ],
        switches=[
            PackPreviewSwitch(
                id=sw.id, values=list(sw.values), default=sw.default, label=dict(sw.label) if sw.label else None
            )
            for sw in options.switches
        ],
        examples=[
            PackPreviewExample(
                id=ex.id,
                source="file" if ex.source == "file" else "auto",
                label=dict(ex.label) if ex.label else None,
                error=ex.error,
                defaults=dict(ex.data.defaults) if ex.data is not None else {},
            )
            for ex in options.examples
        ],
        default_example=options.default_example,
        combination=dict(options.combination),
    )


def preview_build_response(build: PreviewBuild) -> PackPreviewBuildResponse:
    return PackPreviewBuildResponse(
        id=str(build.id),
        workspace_id=str(build.workspace_id),
        pack=build.pack,
        template=build.template,
        version=build.version,
        document=build.document,
        example=build.example,
        combination=dict(build.combination),
        key=build.key,
        status=build.status.value,
        cached=build.cached,
        created_at=build.created_at,
        started_at=build.started_at,
        finished_at=build.finished_at,
        pages=build.pages,
        error=None if build.error is None else PackPreviewErrorBody(code=build.error.code, detail=build.error.detail),
        source_file=build.source_file,
        has_anchors=build.has_anchors,
    )


@router.get(_PREVIEW, response_model=PackPreviewOptionsResponse)
async def get_preview_options(  # noqa: PLR0913 — путь версии
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    previews: FromDishka[PackPreviewService],
    response: Response,
) -> PackPreviewOptionsResponse:
    """Документы версии, переключатели комбинаций, наборы данных и комбинация по умолчанию (6.1, 6.2)."""
    response.headers.update(_NO_STORE)
    options = await previews.options(require_actor(), workspace_id, pack, template, version)
    return preview_options_response(workspace_id, pack, template, version, options)


@router.post(_PREVIEW, status_code=202, response_model=PackPreviewStartResponse)
async def start_preview(  # noqa: PLR0913 — путь версии и тело
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: StartPackPreviewRequest,
    previews: FromDishka[PackPreviewService],
    response: Response,
) -> PackPreviewStartResponse:
    """Сборка документов в комбинации: 202, ход по `previews/{id}`; 200, если всё взято из кэша."""
    builds = await previews.start(
        require_actor(),
        workspace_id,
        pack,
        template,
        version,
        StartPreviewInput(documents=body.documents, example=body.example, combination=body.combination),
    )
    if all(build.status.is_terminal for build in builds):
        response.status_code = 200
    return PackPreviewStartResponse(builds=[preview_build_response(build) for build in builds])


@router.get(_BUILD, response_model=PackPreviewBuildResponse)
async def get_preview(
    workspace_id: UUID, build_id: UUID, previews: FromDishka[PackPreviewService], response: Response
) -> PackPreviewBuildResponse:
    response.headers.update(_NO_STORE)
    return preview_build_response(await previews.get(require_actor(), workspace_id, build_id))


@router.delete(_BUILD, response_model=PackPreviewBuildResponse)
async def cancel_preview(
    workspace_id: UUID, build_id: UUID, previews: FromDishka[PackPreviewService]
) -> PackPreviewBuildResponse:
    """Отмена идущей сборки; законченную возвращает как есть."""
    return preview_build_response(await previews.cancel(require_actor(), workspace_id, build_id))


@router.get(_BUILD + "/pdf", response_model=None)
async def get_preview_pdf(workspace_id: UUID, build_id: UUID, previews: FromDishka[PackPreviewService]) -> Response:
    """PDF удачной сборки; иначе 409 `preview_not_ready`. Содержимое по id сборки не меняется."""
    path = await previews.pdf(require_actor(), workspace_id, build_id)
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "private, max-age=3600"})


@router.get(_BUILD + "/log", response_class=PlainTextResponse)
async def get_preview_log(
    workspace_id: UUID, build_id: UUID, previews: FromDishka[PackPreviewService]
) -> PlainTextResponse:
    """Журнал сборки: предупреждения рендера (`[render]`), вывод latexmk и объяснение неудачи."""
    text = await previews.log(require_actor(), workspace_id, build_id)
    return PlainTextResponse(text, headers=_NO_STORE)


@router.get(_BUILD + "/anchors", response_model=None)
async def get_preview_anchors(workspace_id: UUID, build_id: UUID, previews: FromDishka[PackPreviewService]) -> Response:
    """Якоря мест подписей и меток даты собранного PDF (тот же `anchors.json`, что у сборки проекта)."""
    data = await previews.anchors(require_actor(), workspace_id, build_id)
    return Response(content=data, media_type="application/json", headers=_NO_STORE)
