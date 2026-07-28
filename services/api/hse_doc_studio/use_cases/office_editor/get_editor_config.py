from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import (
    IAIProviderRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.infra.docker.siblings import Reachability
from hse_doc_studio.infra.office import jwt as office_jwt
from hse_doc_studio.infra.office.convert_manager import OFFICE_DOCUMENT_TYPES
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.use_cases.office_editor.ai_settings import build_ai_plugin_settings
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    resolve_active_office_image,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_KEY_SAFE_RE = re.compile(r"[^0-9a-zA-Z._-]")
_KEY_MAX_LEN = 128
_API_JS_PATH = "/web-apps/apps/api/documents/api.js"
# Куда фронт ведёт из карточки «Слайды» при state=image_missing: секция
# настроек, где живёт управление образами офисных сервисов (константа).
_SETTINGS_SECTION = "presentations"


class NotOfficeDocumentError(Exception):
    """Артефакт документа не в офисном формате (word/cell/slide) — в
    DS-редакторе открывать нечего."""


@dataclass
class GetOfficeEditorConfigInput:
    project_id: UUID
    doc_id: str


@dataclass
class GetOfficeEditorConfigOutput:
    # "ready" | "image_missing" | "unavailable" — см. контракт office-editor.
    state: str
    editor_base_url: str | None = None
    api_js_url: str | None = None
    config: dict[str, Any] | None = None
    image: str | None = None
    detail: str | None = None
    # Константа: при image_missing фронт ведёт в эту секцию настроек.
    settings_section: str = _SETTINGS_SECTION


def build_document_key(doc_id: str, mtime_ns: int, size: int) -> str:
    """DS document key: стабилен для версии файла, меняется после каждой правки.

    DS кэширует документ по key — новый key после изменения файла (mtime/size)
    заставляет редактор перечитать актуальные байты. Алфавит и длина — по
    требованиям DS ([0-9a-zA-Z._-], ≤128).
    """
    raw = f"{doc_id}-{mtime_ns}-{size}"
    sanitized = _KEY_SAFE_RE.sub("-", raw)
    if len(sanitized) > _KEY_MAX_LEN:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        sanitized = f"{sanitized[: _KEY_MAX_LEN - len(digest) - 1]}-{digest}"
    return sanitized


def callback_signature(secret: str, project_id: UUID, doc_id: str) -> str:
    """HMAC-подпись query-строки колбэка: DS не может подменить project/doc."""
    return hmac.new(secret.encode("utf-8"), f"{project_id}:{doc_id}".encode(), hashlib.sha256).hexdigest()


class GetOfficeEditorConfigUC:
    """Собирает полный конфиг DocsAPI.DocEditor для документа проекта в
    офисном формате (шаблонный pptx-вариант презентации ИЛИ кастомный
    word/cell/slide-файл, замещающий шаблонный вывод целиком).

    Блокирующая часть — manager.ensure_running(): холодный старт DS занимает
    до ~3 минут, фронт обязан ждать со спиннером (см. контракт).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        manager: OfficeEditorManager,
        reachability: Reachability,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository | None = None,
    ) -> None:
        self._template_repo = template_repo
        self._template_service = ProjectTemplateService()
        self._manager = manager
        self._settings_repo = settings_repo
        self._ai_provider_repo = ai_provider_repo
        # Как DS-контейнер достучится до ЭТОГО бэкенда (скачивание документа +
        # save-колбэк). Спрашивается в момент выдачи конфига, а не при сборке
        # контейнера DI: ответ зависит от того, поднялась ли общая docker-сеть,
        # а это выясняется уже в рантайме.
        self._reachability = reachability
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    def _resolve_output_file(self, project: Any, doc: Any, version: Any) -> str:
        if doc.custom_file is not None:
            return doc.custom_file.stored_path
        _source_file, output_file = self._template_service.resolve_instance_source(project, doc, version)
        return output_file

    async def execute(self, inp: GetOfficeEditorConfigInput) -> GetOfficeEditorConfigOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document '{inp.doc_id}' not found in project {inp.project_id}",
                )
            )

        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )
        doc_def = self._template_service.find_definition(version, doc)
        output_file = self._resolve_output_file(project, doc, version)
        doc_type = OFFICE_DOCUMENT_TYPES.get(PurePosixPath(output_file).suffix.lower())
        if doc_type is None:
            raise NotOfficeDocumentError(
                localized_error(
                    f"Артефакт документа {inp.doc_id!r} не в офисном формате: {output_file}",
                    f"Document '{inp.doc_id}' artifact is not an office format: {output_file}",
                )
            )
        file_type, document_type = doc_type

        artifact = project.folder / output_file
        if not artifact.is_file():
            raise NotFoundError(
                localized_error(
                    f"Файл артефакта не найден: {output_file}",
                    f"Artifact file not found: {output_file}",
                )
            )

        # Состояние движка: образ не установлен (opt-in) vs docker/старт умер.
        # Эффективный образ — runtime-выбор из настроек (office_editor_image),
        # дефолт — образ из api-конфига.
        active_image = resolve_active_office_image(self._settings_repo, "editor")
        if await self._manager.is_image_missing(active_image):
            return GetOfficeEditorConfigOutput(state="image_missing", image=active_image)
        base = await self._manager.ensure_running(active_image)
        if base is None:
            return GetOfficeEditorConfigOutput(
                state="unavailable",
                detail="Docker is unavailable or the Document Server container failed to start",
            )

        await self._sync_ai_plugin(base)

        stat = artifact.stat()
        key = build_document_key(inp.doc_id, stat.st_mtime_ns, stat.st_size)
        title = self._resolve_title(doc, doc_def, doc.chosen_variant, output_file)
        secret = self._manager.jwt_secret
        sig = callback_signature(secret, inp.project_id, inp.doc_id)
        backend_base = (await self._reachability.base_url()).rstrip("/")
        callback_url = (
            f"{backend_base}/api/v1/office-editor/callback"
            f"?project_id={inp.project_id}&doc_id={quote(inp.doc_id)}&sig={sig}"
        )
        config: dict[str, Any] = {
            "document": {
                "fileType": file_type,
                "key": key,
                "title": title,
                "url": f"{backend_base}/api/v1/projects/{inp.project_id}/files/{quote(output_file)}",
            },
            "documentType": document_type,
            "editorConfig": {
                "mode": "edit",
                "lang": current_interface_language().value,
                "callbackUrl": callback_url,
                "user": {"id": "hse-studio", "name": self._resolve_user_name(project, doc)},
                "customization": {
                    "autosave": True,
                    "forcesave": True,
                    "compactHeader": True,
                    "hideRightMenu": False,
                },
            },
        }
        config["token"] = office_jwt.sign(config, secret)
        return GetOfficeEditorConfigOutput(
            state="ready",
            editor_base_url=base,
            api_js_url=f"{base}{_API_JS_PATH}",
            config=config,
        )

    async def _sync_ai_plugin(self, base: str) -> None:
        """Наши AI-провайдеры/модели → серверные настройки AI-плагина DS.

        Настройки применяются при коннекте редактора, поэтому реконсиляция
        живёт именно здесь — перед выдачей конфига новой сессии (aiSettings +
        прокси /ai-proxy: api-ключи остаются на стороне DS, в браузер не
        попадают). Best-effort: без синка редактор всё равно открывается,
        AI-плагин просто остаётся в пользовательском режиме.
        """
        if self._ai_provider_repo is None:
            return
        desired = build_ai_plugin_settings(self._ai_provider_repo.list_all(), self._settings_repo.get())
        await self._manager.apply_ai_settings(desired)

    def _resolve_title(self, doc: Any, doc_def: Any, chosen_variant: str | None, output_file: str) -> str:
        """Кастомный файл — исходное имя загрузки; иначе локализованное
        output_name варианта, fallback — имя файла артефакта."""
        if doc.custom_file is not None:
            return doc.custom_file.original_filename
        names: dict[str, str] = {}
        if doc_def is not None:
            if doc_def.variants:
                variant = next((v for v in doc_def.variants if v.id == chosen_variant), doc_def.variants[0])
                names = dict(variant.output_name or {})
            if not names:
                names = dict(doc_def.output_name or {})
        lang = current_interface_language().value
        title = names.get(lang) or names.get("ru") or next(iter(names.values()), "")
        return title or PurePosixPath(output_file).name

    @staticmethod
    def _resolve_user_name(project: Any, doc: Any) -> str:
        """Имя автора-владельца дока (team) или имя проекта."""
        if doc.owner:
            author = next((a for a in project.authors if a.slug == doc.owner), None)
            if author is not None and author.name:
                return str(author.name)
        if project.authors and project.authors[0].name:
            return str(project.authors[0].name)
        return str(project.name)
