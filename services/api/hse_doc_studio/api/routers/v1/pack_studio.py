"""`/api/v1/pack-studio/*`: Студия шаблонов, срез T5 (docs/design/template-studio.md, разделы 4 и 12).

Гард раздела (`pack_studio_guard`) стоит на всех маршрутах рабочих пространств: раздел выключен (404
`pack_studio_disabled`), токен без области `packs` (403 `pack_scope_required`), нет права «Автор шаблонов» (403
`pack_studio_forbidden`). Состояние раздела (`/pack-studio/section`) открыто любому вошедшему: по нему интерфейс
решает, показывать ли раздел и переключатель в Настройках.

Файлы адресуются путём от папки паков пространства:
`files/hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`.

Мастер «Новая версия» (срез T10): `templates/{pack}/{template}/versions` даёт базы и номера (GET) и создаёт черновик
(POST); `versions/{pack}/{template}/{version}/state` живой класс, номера и заметки, дальше `notes`, `renumber`,
`move-edits` (7.3) и `release`.

Пак и шаблон с нуля (срез T15): `scaffold` даёт источники копии и значения по умолчанию, `packs` создаёт пак с первым
шаблоном, `packs/{pack}/templates` шаблон в существующем паке (заготовка «Минимальный» или копия версии).

Предпросмотр (срез T7): `versions/{pack}/{template}/{version}/preview` отдаёт документы, переключатели и наборы данных
(GET) и запускает сборку (POST); ход сборки, PDF, журнал и якоря мест подписей по `previews/{build_id}`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.files import _content_type_for
from hse_doc_studio.api.schemas.pack_studio import (
    CreatePackRequest,
    CreatePackTemplateRequest,
    CreatePackVersionRequest,
    CreatePackWorkspaceRequest,
    OpenPackOfficialRequest,
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
    PackLocalizedList,
    PackLocalizedText,
    PackMacroHintResponse,
    PackMaintainer,
    PackMetaFieldHintResponse,
    PackMoveEditsRequest,
    PackOfficialRepo,
    PackOfficialResponse,
    PackPreviewBuildResponse,
    PackPreviewCheck,
    PackPreviewDocument,
    PackPreviewErrorBody,
    PackPreviewExample,
    PackPreviewOptionsResponse,
    PackPreviewStartResponse,
    PackPreviewSwitch,
    PackProposeRequest,
    PackProposeResponse,
    PackPullRequest,
    PackReleaseRequest,
    PackReleaseResponse,
    PackRenumberRequest,
    PackScaffoldCreatedResponse,
    PackScaffoldOptionsResponse,
    PackScaffoldPack,
    PackScaffoldRequest,
    PackScaffoldSource,
    PackScaffoldTemplate,
    PackScaffoldVersion,
    PackStartOverRequest,
    PackStudioSectionResponse,
    PackTreeFile,
    PackTreePack,
    PackTreeResponse,
    PackTreeTemplate,
    PackTreeVersion,
    PackVersionChoice,
    PackVersionClass,
    PackVersionCreatedResponse,
    PackVersionMovedResponse,
    PackVersionNotesRequest,
    PackVersionNumbers,
    PackVersionOptionsResponse,
    PackVersionReason,
    PackVersionRef,
    PackVersionStateResponse,
    PackWorkspaceErrorBody,
    PackWorkspaceResponse,
    PackYamlPatchRequest,
    PackYamlPatchResponse,
    ReadOnlyReason,
    StartPackPreviewRequest,
    UpdateClassName,
    UpdatePackStudioSectionRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.pack_studio.entities import (
    DiagnosticSeverity,
    PackEditorHints,
    PackLintReport,
    PackTree,
    WorkspaceKind,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.official import OfficialRepo, official_repo
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.preview import PreviewBuild
from hse_doc_studio.core.pack_studio.scaffold import (
    Maintainer,
    NewPack,
    NewTemplate,
    Scaffold,
    ScaffoldKind,
    ScaffoldOptions,
    ScaffoldResult,
    ScaffoldSource,
    SourceOrigin,
)
from hse_doc_studio.core.pack_studio.versions import (
    LANGS,
    LocalizedList,
    NewVersionOptions,
    VersionNotesInput,
    VersionState,
)
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess, SectionView
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService, YamlOp
from hse_doc_studio.use_cases.pack_studio.git import ForkChoice, GitView, PackGitService, ProposeInput
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService
from hse_doc_studio.use_cases.pack_studio.official import OfficialInfo, OfficialPacks
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewOptions, StartPreviewInput
from hse_doc_studio.use_cases.pack_studio.scaffold import CreatePackInput, CreateTemplateInput, PackScaffoldService
from hse_doc_studio.use_cases.pack_studio.versions import CreateVersionInput, PackVersionService, ReleaseInput
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


def _official() -> OfficialRepo | None:
    cfg = settings.pack_studio
    return official_repo(
        cfg.official_repo_url,
        packs_path=cfg.official_packs_path,
        base_branch=cfg.official_base_branch,
        license=cfg.official_license,
    )


def official_repo_response(repo: OfficialRepo | None) -> PackOfficialRepo | None:
    if repo is None:
        return None
    return PackOfficialRepo(
        url=repo.url,
        web_url=repo.web_url,
        packs_path=repo.packs_path,
        base_branch=repo.base_branch,
        license=repo.license,
        license_url=repo.license_url,
        contributing_url=repo.contributing_url,
    )


def official_response(info: OfficialInfo) -> PackOfficialResponse:
    return PackOfficialResponse(
        repo=official_repo_response(info.repo),
        workspace_id=None if info.workspace_id is None else str(info.workspace_id),
    )


def workspace_response(view: WorkspaceView) -> PackWorkspaceResponse:
    ws = view.workspace
    official = _official()
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
        official=official is not None and official.matches(ws.remote_url),
        license_accepted_at=ws.license_accepted_at,
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


@router.get("/pack-studio/official", response_model=PackOfficialResponse)
async def get_official(official: FromDishka[OfficialPacks], response: Response) -> PackOfficialResponse:
    """Официальные паки (срез T22): репозиторий установки (null: кнопки нет) и своё пространство."""
    response.headers.update(_NO_STORE)
    return official_response(await official.info(require_actor()))


@router.post("/pack-studio/official/workspace", response_model=PackWorkspaceResponse)
async def open_official(
    body: OpenPackOfficialRequest, official: FromDishka[OfficialPacks], response: Response
) -> PackWorkspaceResponse:
    """Пространство над официальным репозиторием своим токеном: уже созданное (200) или новое (202, клон в фоне)."""
    view, created = await official.open(require_actor(), body.credential_id)
    response.status_code = 202 if created else 200
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
        ProposeInput(
            title=body.title,
            description=body.description,
            message=body.message,
            fork=fork,
            accept_license=body.accept_license,
        ),
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
        pr_state=report.pr_state.value if report.pr_state else None,
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
        with_checks=build.with_checks,
        checks=None
        if build.checks is None
        else [
            PackPreviewCheck(rule_id=c.rule_id, severity=c.severity, message=c.message, file=c.file, line=c.line)
            for c in build.checks
        ],
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
        StartPreviewInput(
            documents=body.documents, example=body.example, combination=body.combination, checks=body.checks
        ),
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


# ── мастер «Новая версия» ───────────────────────────────────────────────────

_TEMPLATE_VERSIONS = "/pack-studio/workspaces/{workspace_id}/templates/{pack}/{template}/versions"
_VERSION = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}"


def _version_ref(ref: VersionRef) -> PackVersionRef:
    return PackVersionRef(pack=ref.pack, template=ref.template, version=ref.version, path=ref.dir)


def _numbers(numbers: Mapping[TemplateUpdateClass, str]) -> PackVersionNumbers:
    return PackVersionNumbers(
        patch=numbers.get(TemplateUpdateClass.patch),
        minor=numbers.get(TemplateUpdateClass.minor),
        major=numbers.get(TemplateUpdateClass.major),
    )


def _localized(value: LocalizedList) -> PackLocalizedList:
    return PackLocalizedList(ru=list(value.get("ru", ())), en=list(value.get("en", ())))


def _class_name(value: TemplateUpdateClass | None) -> UpdateClassName | None:
    return value.value if value is not None else None


def version_options_response(options: NewVersionOptions) -> PackVersionOptionsResponse:
    return PackVersionOptionsResponse(
        pack=options.template.pack,
        template=options.template.template,
        versions=[
            PackVersionChoice(
                version=c.version, status=c.status, released=c.released, registered=c.registered, modified=c.modified
            )
            for c in options.versions
        ],
        default_base=options.default_base,
        default_version=options.default_version,
        numbers=_numbers(options.numbers),
    )


def version_state_response(state: VersionState) -> PackVersionStateResponse:
    return PackVersionStateResponse(
        version=_version_ref(state.ref),
        status=state.status,
        released=state.released,
        modified=state.modified,
        registered=state.registered,
        release_outdated=state.release_outdated,
        is_default=state.is_default,
        base=state.base,
        minimum=_class_name(state.minimum),
        suggested=_class_name(state.suggested),
        by_number=_class_name(state.by_number),
        declared=_class_name(state.declared),
        note=state.note,
        number_ok=state.number_ok,
        headline=dict(state.headline),
        reasons=[
            PackVersionReason(
                code=r.code,
                path=r.path,
                change=r.change,
                minimum=r.minimum.value,
                suggested=r.suggested.value,
                hard=r.hard,
                exception=r.exception,
                message=dict(r.message),
            )
            for r in state.reasons
        ],
        numbers=_numbers(state.numbers),
        changes=_localized(state.changes),
        breaking_changes=_localized(state.breaking_changes),
        draft_changes=_localized(state.draft_changes),
        draft_breaking=_localized(state.draft_breaking),
        move_to=state.move_to,
        error=state.error,
    )


def _notes_input(body: PackVersionNotesRequest) -> VersionNotesInput:
    def pairs(value: PackLocalizedList | None) -> LocalizedList | None:
        if value is None:
            return None
        return {lang: tuple(getattr(value, lang)) for lang in LANGS}

    return VersionNotesInput(changes=pairs(body.changes), breaking_changes=pairs(body.breaking_changes), note=body.note)


def _update_class(raw: str | None) -> TemplateUpdateClass | None:
    return TemplateUpdateClass(raw) if raw else None


@router.get(_TEMPLATE_VERSIONS, response_model=PackVersionOptionsResponse)
async def get_version_options(
    workspace_id: UUID, pack: str, template: str, versions: FromDishka[PackVersionService], response: Response
) -> PackVersionOptionsResponse:
    """Базы для «Новой версии» (по умолчанию последняя выпущенная) и номера по классам (7.1)."""
    response.headers.update(_NO_STORE)
    return version_options_response(await versions.options(require_actor(), workspace_id, pack, template))


@router.post(_TEMPLATE_VERSIONS, status_code=201, response_model=PackVersionCreatedResponse)
async def create_version(  # noqa: PLR0913 — путь шаблона и тело
    workspace_id: UUID,
    pack: str,
    template: str,
    body: CreatePackVersionRequest,
    versions: FromDishka[PackVersionService],
) -> PackVersionCreatedResponse:
    """Шаг 1 мастера: каталог базы копируется в черновик `beta`, заметки пусты."""
    created = await versions.create(
        require_actor(),
        workspace_id,
        pack,
        template,
        CreateVersionInput(base=body.base, version=body.version, update_class=_update_class(body.update_class)),
    )
    return PackVersionCreatedResponse(
        version=_version_ref(created.ref),
        base=created.base,
        update_class=_class_name(created.update_class),
        warnings=list(created.warnings),
    )


@router.get(_VERSION + "/state", response_model=PackVersionStateResponse)
async def get_version_state(  # noqa: PLR0913 — путь версии
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    versions: FromDishka[PackVersionService],
    response: Response,
) -> PackVersionStateResponse:
    """Живой класс черновика по классификатору (7.2), номера по классам, заметки и их черновик из отчёта (7.4)."""
    response.headers.update(_NO_STORE)
    state = await versions.state(require_actor(), workspace_id, pack, template, version)
    return version_state_response(state)


@router.put(_VERSION + "/notes", response_model=PackVersionStateResponse)
async def put_version_notes(  # noqa: PLR0913 — путь версии и тело
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackVersionNotesRequest,
    versions: FromDishka[PackVersionService],
) -> PackVersionStateResponse:
    """Заметки `changes` и `breaking_changes` ru и en, объяснение класса `release.note`: точечные правки YAML."""
    state = await versions.save_notes(require_actor(), workspace_id, pack, template, version, _notes_input(body))
    return version_state_response(state)


@router.post(_VERSION + "/renumber", response_model=PackVersionMovedResponse)
async def renumber_version(  # noqa: PLR0913 — путь версии и тело
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackRenumberRequest,
    versions: FromDishka[PackVersionService],
) -> PackVersionMovedResponse:
    """Черновик на другой номер: класс поднят или номер уже выпущен в базе (4.3). Мягче минимума нельзя."""
    moved = await versions.renumber(require_actor(), workspace_id, pack, template, version, body.version)
    return PackVersionMovedResponse(
        version=_version_ref(moved.ref), previous=moved.previous, unreleased=moved.unreleased, restored=moved.restored
    )


@router.post(_VERSION + "/move-edits", response_model=PackVersionMovedResponse)
async def move_version_edits(  # noqa: PLR0913 — путь версии и тело
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackMoveEditsRequest,
    versions: FromDishka[PackVersionService],
) -> PackVersionMovedResponse:
    """«Перенести правки в новую версию» (7.3): правки выпущенного каталога уходят в черновик, каталог к выпуску."""
    moved = await versions.move_edits(require_actor(), workspace_id, pack, template, version, body.version)
    return PackVersionMovedResponse(
        version=_version_ref(moved.ref), previous=moved.previous, unreleased=moved.unreleased, restored=moved.restored
    )


@router.post(_VERSION + "/release", response_model=PackReleaseResponse)
async def release_pack_version(  # noqa: PLR0913 — путь версии и тело
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackReleaseRequest,
    versions: FromDishka[PackVersionService],
) -> PackReleaseResponse:
    """«Выпустить»: `status: stable`, `released_at`, `release.kind`, по желанию `default_version`, запись в реестр."""
    released = await versions.release(
        require_actor(),
        workspace_id,
        pack,
        template,
        version,
        ReleaseInput(kind=_update_class(body.kind), set_default=body.set_default),
    )
    return PackReleaseResponse(
        version=_version_ref(released.ref),
        digest=released.digest,
        kind=_class_name(released.kind),
        previous=released.previous,
        replaced=released.replaced,
        default_set=released.default_set,
        edited=list(released.edited),
        warnings=list(released.warnings),
    )


# ── Срез T15: пак и шаблон с нуля ──


def scaffold_options_response(options: ScaffoldOptions) -> PackScaffoldOptionsResponse:
    maintainer = options.maintainer
    return PackScaffoldOptionsResponse(
        sources=[
            PackScaffoldPack(
                origin=p.origin.value,
                pack=p.pack,
                name=dict(p.name),
                license=p.license,
                templates=[
                    PackScaffoldTemplate(
                        template=t.template,
                        name=dict(t.name),
                        default_version=t.default_version,
                        versions=[
                            PackScaffoldVersion(
                                version=v.version, status=v.status, released=v.released, default=v.default
                            )
                            for v in t.versions
                        ],
                    )
                    for t in p.templates
                ],
            )
            for p in options.sources
        ],
        taken_packs=list(options.taken_packs),
        maintainer=(
            PackMaintainer(name=maintainer.name, email=maintainer.email, url=maintainer.url) if maintainer else None
        ),
        license=options.license,
        version=options.version,
    )


def scaffold_created_response(result: ScaffoldResult) -> PackScaffoldCreatedResponse:
    source = result.source
    return PackScaffoldCreatedResponse(
        version=_version_ref(result.ref),
        pack_created=result.pack_created,
        manifests=list(result.manifests),
        main_file=result.main_file,
        files=result.files,
        source=(
            PackScaffoldSource(
                origin=source.origin.value, pack=source.pack, template=source.template, version=source.version
            )
            if source is not None
            else None
        ),
    )


def _text(value: PackLocalizedText | None) -> dict[str, str] | None:
    return {"ru": value.ru, "en": value.en} if value is not None else None


def _scaffold(body: PackScaffoldRequest) -> Scaffold:
    source = body.source
    return Scaffold(
        kind=ScaffoldKind(body.kind),
        source=(
            ScaffoldSource(SourceOrigin(source.origin), source.pack, source.template, source.version)
            if source is not None and body.kind == "copy"
            else None
        ),
    )


def _new_template(
    id_: str, name: PackLocalizedText, short: PackLocalizedText | None, description: PackLocalizedText | None
) -> NewTemplate:
    return NewTemplate(id=id_, name=_text(name) or {}, short_name=_text(short), description=_text(description))


@router.get("/pack-studio/workspaces/{workspace_id}/scaffold", response_model=PackScaffoldOptionsResponse)
async def get_scaffold_options(
    workspace_id: UUID, scaffold: FromDishka[PackScaffoldService], response: Response
) -> PackScaffoldOptionsResponse:
    """Источники копии (паки пространства и каталога Студии), занятые id, сопровождающий и номер по умолчанию."""
    response.headers.update(_NO_STORE)
    return scaffold_options_response(await scaffold.options(require_actor(), workspace_id))


@router.post(
    "/pack-studio/workspaces/{workspace_id}/packs", status_code=201, response_model=PackScaffoldCreatedResponse
)
async def create_pack(
    workspace_id: UUID, body: CreatePackRequest, scaffold: FromDishka[PackScaffoldService]
) -> PackScaffoldCreatedResponse:
    """Новый пак с первым шаблоном: заготовка «Минимальный» или копия версии с новыми id (раздел 8)."""
    maintainer = body.maintainer
    pack = NewPack(
        id=body.id,
        name=_text(body.name) or {},
        description=_text(body.description),
        maintainer=Maintainer(maintainer.name, maintainer.email, maintainer.url) if maintainer else None,
        license=body.license or "",
        source=body.source,
        template=_new_template(
            body.template.id, body.template.name, body.template.short_name, body.template.description
        ),
    )
    result = await scaffold.create_pack(
        require_actor(),
        workspace_id,
        CreatePackInput(pack=pack, scaffold=_scaffold(body.scaffold), version=body.version),
    )
    return scaffold_created_response(result)


@router.post(
    "/pack-studio/workspaces/{workspace_id}/packs/{pack}/templates",
    status_code=201,
    response_model=PackScaffoldCreatedResponse,
)
async def create_pack_template(
    workspace_id: UUID, pack: str, body: CreatePackTemplateRequest, scaffold: FromDishka[PackScaffoldService]
) -> PackScaffoldCreatedResponse:
    """Новый шаблон в существующем паке пространства: то же, что у нового пака, на уровне шаблона."""
    template = _new_template(body.id, body.name, body.short_name, body.description)
    result = await scaffold.create_template(
        require_actor(),
        workspace_id,
        pack,
        CreateTemplateInput(template=template, scaffold=_scaffold(body.scaffold), version=body.version),
    )
    return scaffold_created_response(result)
