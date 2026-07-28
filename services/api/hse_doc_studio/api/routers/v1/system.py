from __future__ import annotations

import platform
import shutil
from pathlib import Path
from typing import Literal

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.update.repositories import IReleaseNotesRepository, ISelfUpdateGateway
from hse_doc_studio.infra.runtime.environment import in_container
from hse_doc_studio.infra.submission.assembler import available_archive_formats
from hse_doc_studio.infra.update.deployment import DeploymentMode, deployment_mode, docker_alive
from hse_doc_studio.infra.update.self_update_gateway import is_valid_version
from hse_doc_studio.use_cases.system.check_updates import CheckUpdatesUC
from hse_doc_studio.use_cases.system.get_update_status import GetUpdateStatusUC
from hse_doc_studio.use_cases.system.list_versions import ListVersionsUC

router = APIRouter(route_class=DishkaRoute)

EditorId = Literal["cursor", "vscode"]
OsName = Literal["windows", "macos", "linux", "other"]


class RunnerHealthResponse(BaseModel):
    docker: Literal["running", "stopped"]


class SystemInfoResponse(BaseModel):
    version: str
    # ISO-8601 build timestamp baked into the image by CI; "" in a source run.
    built: str
    deployment_mode: DeploymentMode
    os: OsName
    os_version: str
    python_version: str
    image_ref: str | None
    source_url: str
    github_repo: str
    license: str
    docker: Literal["running", "stopped"]
    # One-click self-update is available only in all-in-one mode with a
    # reachable Docker daemon; otherwise the UI falls back to a copy-command.
    can_self_update: bool
    # Absolute path of the app data dir (global config, AI providers, chats…),
    # so the About screen can show it and offer "open in editor".
    data_dir: str
    # Update state from the LAST check (no network here — About is opened often;
    # the network hit lives behind POST /system/check-updates).
    latest_version: str
    update_available: bool
    update_checked_at: str | None
    # What the available version brings, as the last check found it. The curated
    # notes (GET /system/release-notes) only cover versions this build ships with,
    # so a pending update's notes can only come from the feed — and are cached here.
    latest_release_date: str
    latest_release_notes: list[str]
    # False in an air-gapped install (HSE_STUDIO__UPDATE_FEED_URL=off) — the UI
    # then hides the check button instead of offering a call that can't work.
    update_feed_enabled: bool


class ReleaseEntryResponse(BaseModel):
    version: str
    date: str
    # Notes in the interface language, from the curated bilingual changelog.
    notes: list[str]


class ReleaseNotesResponse(BaseModel):
    releases: list[ReleaseEntryResponse]


class CheckUpdatesResponse(BaseModel):
    current: str
    latest: str
    available: bool
    # False → the feed didn't answer (disabled/unreachable/rate-limited) and
    # `latest` comes from the last successful check; `reason` says why.
    checked: bool
    checked_at: str | None
    reason: str


class VersionOptionResponse(BaseModel):
    version: str
    date: str
    notes: list[str]
    installed: bool
    # Новее установленной; иначе переключение на эту версию — откат назад.
    newer: bool


class VersionsResponse(BaseModel):
    current: str
    checked_at: str | None
    versions: list[VersionOptionResponse]


class SelfUpdateRequest(BaseModel):
    version: str


class SelfUpdateResponse(BaseModel):
    started: bool
    target_image: str


class EditorEntry(BaseModel):
    id: EditorId
    label: str
    scheme: str
    available: bool


class EditorsResponse(BaseModel):
    os: OsName
    editors: list[EditorEntry]


class ArchiveFormatEntry(BaseModel):
    id: Literal["zip", "targz", "7z", "rar"]
    label: str
    ext: str
    available: bool


class ArchiveFormatsResponse(BaseModel):
    formats: list[ArchiveFormatEntry]


# ---------------------------------------------------------------- docker health


@router.get("/system/runner-health", response_model=RunnerHealthResponse)
async def runner_health() -> RunnerHealthResponse:
    alive = await docker_alive()
    return RunnerHealthResponse(docker="running" if alive else "stopped")


# ---------------------------------------------------------------- editors


def _detect_os() -> OsName:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    return "other"


# Each editor declares per-OS detection hints:
#   - cli_names: try shutil.which() for these (shutil.which respects PATHEXT on
#     Windows, so "code" matches "code.cmd")
#   - app_paths: well-known absolute install locations (covers e.g. macOS where
#     the CLI shim isn't on PATH by default)
_EDITOR_REGISTRY: dict[EditorId, dict[str, str | dict[OsName, list[str]]]] = {
    "cursor": {
        "label": "Cursor",
        "scheme": "cursor",
        "cli_names": {
            "windows": ["cursor", "cursor.cmd"],
            "macos": ["cursor"],
            "linux": ["cursor"],
            "other": ["cursor"],
        },
        "app_paths": {
            "windows": [],
            "macos": ["/Applications/Cursor.app"],
            "linux": [],
            "other": [],
        },
    },
    "vscode": {
        "label": "VS Code",
        "scheme": "vscode",
        "cli_names": {
            "windows": ["code", "code.cmd"],
            "macos": ["code"],
            "linux": ["code"],
            "other": ["code"],
        },
        "app_paths": {
            "windows": [],
            "macos": ["/Applications/Visual Studio Code.app"],
            "linux": ["/usr/share/code", "/snap/code"],
            "other": [],
        },
    },
}


def _is_available(os_name: OsName, spec: dict[str, str | dict[OsName, list[str]]]) -> bool:
    # В контейнере искать редактор бессмысленно: `which` смотрит НАШ PATH, а
    # редактор стоит у пользователя на хосте — кнопка «открыть папку» оказывалась
    # выключена всегда и ни для кого. Ссылку `vscode://` открывает браузер НА
    # ХОСТЕ, так что предлагаем оба варианта и отдаём решение системе: не
    # зарегистрирована схема — просто ничего не произойдёт.
    if in_container():
        return True

    cli_names_by_os = spec["cli_names"]
    assert isinstance(cli_names_by_os, dict)  # noqa: S101
    for cli in cli_names_by_os.get(os_name, []):
        if shutil.which(cli) is not None:
            return True

    app_paths_by_os = spec["app_paths"]
    assert isinstance(app_paths_by_os, dict)  # noqa: S101
    return any(Path(app_path).exists() for app_path in app_paths_by_os.get(os_name, []))


@router.get("/system/editors", response_model=EditorsResponse)
async def list_editors() -> EditorsResponse:
    os_name = _detect_os()
    entries: list[EditorEntry] = []
    for editor_id, spec in _EDITOR_REGISTRY.items():
        label = spec["label"]
        scheme = spec["scheme"]
        assert isinstance(label, str)  # noqa: S101
        assert isinstance(scheme, str)  # noqa: S101
        entries.append(
            EditorEntry(
                id=editor_id,
                label=label,
                scheme=scheme,
                available=_is_available(os_name, spec),
            )
        )
    return EditorsResponse(os=os_name, editors=entries)


# ---------------------------------------------------------------- archive formats


@router.get("/system/archive-formats", response_model=ArchiveFormatsResponse)
async def list_archive_formats() -> ArchiveFormatsResponse:
    # zip/tar.gz are always available; 7z/rar depend on an external CLI being on
    # PATH (probed via shutil.which inside the assembler).
    return ArchiveFormatsResponse(
        formats=[ArchiveFormatEntry.model_validate(fmt) for fmt in available_archive_formats()]
    )


# ---------------------------------------------------------------- system info


def _image_ref(mode: DeploymentMode) -> str | None:
    """Ссылка на образ, из которого мы запущены.

    Образ ОДИН (`image_base:<версия>`) — суффиксы `/all-in-one` и `/api` остались
    от прежней раскладки из трёх образов и указывали на несуществующие ссылки.
    """
    if mode == "native":
        return None  # native dev run — no container image
    return f"{settings.image_base}:{settings.get_app_version()}"


@router.get("/system/info", response_model=SystemInfoResponse)
async def system_info(
    uc: FromDishka[GetUpdateStatusUC],
    updater: FromDishka[ISelfUpdateGateway],
    paths: FromDishka[PathMapping],
) -> SystemInfoResponse:
    mode = deployment_mode(settings.static_dir)
    update = await uc.execute()
    return SystemInfoResponse(
        version=settings.get_app_version(),
        built=settings.built,
        deployment_mode=mode,
        os=_detect_os(),
        os_version=platform.version(),
        python_version=platform.python_version(),
        image_ref=_image_ref(mode),
        source_url=settings.source_url,
        github_repo=settings.github_repo,
        license=settings.license_name,
        docker="running" if await docker_alive() else "stopped",
        # Одна и та же проверка, что и у автообновления (см. ISelfUpdateGateway):
        # кнопка не должна обещать того, чего фоновый апдейтер не сделает.
        can_self_update=await updater.can_self_update(),
        # Путь показывается пользователю, чтобы он нашёл каталог У СЕБЯ (там его
        # настройки, и их положено бэкапить) — значит и путь нужен хостовый, а не
        # внутренний `/data`, которого на его машине нет.
        data_dir=paths.display(str(settings.data_dir)),
        latest_version=update.latest,
        update_available=update.available,
        update_checked_at=update.checked_at.isoformat() if update.checked_at else None,
        update_feed_enabled=update.feed_enabled,
        latest_release_date=update.latest_date,
        latest_release_notes=list(update.latest_notes),
    )


@router.get("/system/release-notes", response_model=ReleaseNotesResponse)
async def release_notes(repo: FromDishka[IReleaseNotesRepository]) -> ReleaseNotesResponse:
    # Локальные данные сборки, прочитанные из release-notes.json на старте: сети
    # здесь нет вовсе, поэтому «Что нового» открывается и в закрытом контуре.
    return ReleaseNotesResponse(
        releases=[
            ReleaseEntryResponse(version=entry.version, date=entry.date, notes=list(entry.notes))
            for entry in repo.list(current_interface_language())
        ]
    )


@router.post("/system/check-updates", response_model=CheckUpdatesResponse)
async def check_updates(uc: FromDishka[CheckUpdatesUC]) -> CheckUpdatesResponse:
    # POST, а не GET: запрос ходит в сеть и перезаписывает кэш последней проверки —
    # это действие по кнопке, а не чтение, и кэшировать его посредникам незачем.
    result = await uc.execute()
    return CheckUpdatesResponse(
        current=result.current,
        latest=result.latest,
        available=result.available,
        checked=result.checked,
        checked_at=result.checked_at.isoformat() if result.checked_at else None,
        reason=result.reason,
    )


@router.get("/system/versions", response_model=VersionsResponse)
async def list_versions(uc: FromDishka[ListVersionsUC]) -> VersionsResponse:
    # Список того, на что можно переключиться, — из кэша последней проверки, без
    # сети (обновляет его POST /system/check-updates).
    result = await uc.execute()
    return VersionsResponse(
        current=result.current,
        checked_at=result.checked_at.isoformat() if result.checked_at else None,
        versions=[
            VersionOptionResponse(
                version=option.version,
                date=option.date,
                notes=list(option.notes),
                installed=option.installed,
                newer=option.newer,
            )
            for option in result.versions
        ],
    )


@router.post("/system/self-update", status_code=202, response_model=SelfUpdateResponse)
async def self_update(
    body: SelfUpdateRequest,
    updater: FromDishka[ISelfUpdateGateway],
) -> SelfUpdateResponse:
    """Переключить установку на указанную версию — вперёд или назад.

    Занятость (идущая сборка, ход агента) здесь НЕ проверяется, в отличие от
    автообновления: пользователь нажал сам и видит, что происходит на экране.
    Несуществующий тег безопасен — апдейтер не сможет его скачать и оставит
    работающий контейнер нетронутым.
    """
    if not await updater.can_self_update():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "not_self_updatable",
                "detail": "Переключение версии доступно только в режиме all-in-one с доступным Docker.",
            },
        )
    if not is_valid_version(body.version):
        raise HTTPException(status_code=400, detail="invalid version")

    if not await updater.start(body.version):
        raise HTTPException(
            status_code=409,
            detail={"code": "self_update_failed", "detail": "Не удалось запустить обновление."},
        )
    return SelfUpdateResponse(started=True, target_image=updater.target_image(body.version))
