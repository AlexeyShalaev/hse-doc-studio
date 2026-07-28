from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import OfficeConvertConfig, OfficeEditorConfig, settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import (
    DockerImageManager,
    LocalImageInfo,
)

# Офисные сервисы с управляемыми образами: "convert" — Gotenberg
# (pptx→PDF-предпросмотр), "editor" — ONLYOFFICE Document Server (in-app
# редактор). Зеркало LanguageTool-блюпринта (use_cases/languagetool/*).
OFFICE_SERVICES: tuple[str, ...] = ("convert", "editor")

# Runtime-настройка (config.json), переопределяющая деплой-дефолт из api.config.
_SETTINGS_KEYS: dict[str, str] = {
    "convert": "office_convert_image",
    "editor": "office_editor_image",
}

# Подсказка фронту, чем является сервис (иконка/копирайтинг), не для логики.
_LABEL_HINTS: dict[str, str] = {
    "convert": "gotenberg",
    "editor": "onlyoffice",
}


def office_service_config(service: str) -> OfficeConvertConfig | OfficeEditorConfig:
    """Деплой-конфиг сервиса (image-дефолт + allowlist + Docker Hub base)."""
    if service == "convert":
        return settings.office_convert
    if service == "editor":
        return settings.office_editor
    raise ValueError(localized_error(f"неизвестный офисный сервис: {service}", f"unknown office service: {service}"))


def office_service_settings_key(service: str) -> str:
    """Ключ runtime-настройки (config.json) с выбранным пользователем образом."""
    key = _SETTINGS_KEYS.get(service)
    if key is None:
        raise ValueError(
            localized_error(f"неизвестный офисный сервис: {service}", f"unknown office service: {service}")
        )
    return key


def office_service_label_hint(service: str) -> str:
    hint = _LABEL_HINTS.get(service)
    if hint is None:
        raise ValueError(
            localized_error(f"неизвестный офисный сервис: {service}", f"unknown office service: {service}")
        )
    return hint


def resolve_active_office_image(settings_repo: ISettingsRepository, service: str) -> str:
    """Return the image the managed office-service container will run.

    User-configured `office_convert_image` / `office_editor_image` in
    config.json wins; if absent or empty we fall back to the deployment-level
    default in api.config (mirrors `resolve_active_languagetool_image`).
    """
    cfg = office_service_config(service)
    stored = settings_repo.get()
    choice = stored.get(office_service_settings_key(service))
    if isinstance(choice, str) and choice.strip():
        return choice
    return cfg.image


def office_repo_allowed(image: str, allowed: list[str]) -> bool:
    """True if `image` is a tagged ref whose repo is in the service allowlist."""
    if ":" not in image:
        return False
    repo, _, _ = image.partition(":")
    return repo in allowed


@dataclass
class ListOfficeServiceImagesInput:
    service: str


@dataclass
class ListOfficeServiceImagesOutput:
    service: str
    active_image: str
    allowed_repos: list[str]
    installed: list[LocalImageInfo]


class ListOfficeServiceImagesUC:
    """Lists installed images of an office service + the active one.

    Reuses the repo-agnostic DockerImageManager — same `docker images` calls
    as the compile/LanguageTool image lists, scoped to the service allowlist.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self, inp: ListOfficeServiceImagesInput) -> ListOfficeServiceImagesOutput:
        cfg = office_service_config(inp.service)
        active = resolve_active_office_image(self._settings_repo, inp.service)
        installed: list[LocalImageInfo] = []
        for repo in cfg.allowed_repos:
            installed.extend(await self._image_manager.list_local(repo))
        return ListOfficeServiceImagesOutput(
            service=inp.service,
            active_image=active,
            allowed_repos=list(cfg.allowed_repos),
            installed=installed,
        )
