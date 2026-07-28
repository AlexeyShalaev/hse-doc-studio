from __future__ import annotations

import asyncio
import hmac
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.infra.office import jwt as office_jwt
from hse_doc_studio.infra.office.convert_manager import CONVERTIBLE_OFFICE_EXTS, OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.use_cases.files.put_file import PutFileInput, PutFileUC
from hse_doc_studio.use_cases.office_editor.get_editor_config import callback_signature
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    resolve_active_office_image,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_DOWNLOAD_TIMEOUT_S = 120.0

# DS callback statuses (https://api.onlyoffice.com/docs/docs-api/usage-api/callback-handler/).
_STATUS_EDITING = 1
_STATUS_SAVE = 2
_STATUS_SAVE_ERROR = 3
_STATUS_CLOSED = 4
_STATUS_FORCE_SAVE = 6
_STATUS_FORCE_SAVE_ERROR = 7


@dataclass
class OfficeEditorCallbackInput:
    project_id: UUID
    doc_id: str
    sig: str
    body: dict[str, Any]
    authorization: str | None = None


class OfficeEditorCallbackUC:
    """Приёмник колбэков Document Server (вызывает только DS-контейнер).

    Двойная проверка подлинности: HMAC-подпись query-строки (`sig` из нашего
    же callbackUrl — DS не может подменить project/doc) плюс JWT самого DS
    (тело или Authorization-заголовок). Сохранение (status 2/6): скачиваем
    документ у DS (его self-URL переписывается на наш published-адрес) и пишем
    байты через put-file — путь резолвится заново по шаблону, колбэку путь не
    доверяем; правка попадает в ProjectVCS. После записи фоново пересоздаётся
    соседний PDF-предпросмотр (Gotenberg) — «Превью» подхватывает правки без
    полной пересборки.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        manager: OfficeEditorManager,
        put_file_uc: PutFileUC,
        convert_manager: OfficeConvertManager,
        settings_repo: ISettingsRepository,
        client: httpx.Client,
    ) -> None:
        self._template_repo = template_repo
        self._template_service = ProjectTemplateService()
        self._manager = manager
        self._put_file_uc = put_file_uc
        self._convert_manager = convert_manager
        self._settings_repo = settings_repo
        self._client = client
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        # Фоновые задачи доконвертации: держим ссылки, чтобы event loop их не
        # собрал до завершения (стандартная ловушка create_task).
        self._preview_tasks: set[asyncio.Task[None]] = set()

    async def execute(self, inp: OfficeEditorCallbackInput) -> dict[str, int]:
        self._verify_auth(inp)

        status = inp.body.get("status")
        key = str(inp.body.get("key") or "")
        if status == _STATUS_EDITING:
            self._manager.mark_active(key)
        elif status == _STATUS_CLOSED:
            self._manager.mark_closed(key)
        elif status in (_STATUS_SAVE, _STATUS_FORCE_SAVE):
            await self._save(inp, key)
        elif status in (_STATUS_SAVE_ERROR, _STATUS_FORCE_SAVE_ERROR):
            logger.warning(
                "office-editor: DS reported save error",
                status=status,
                doc_id=inp.doc_id,
                project_id=str(inp.project_id),
            )
        else:
            logger.debug("office-editor: callback with unhandled status", status=status)
        return {"error": 0}

    # ── auth ────────────────────────────────────────────────────────────────

    def _verify_auth(self, inp: OfficeEditorCallbackInput) -> None:
        secret = self._manager.jwt_secret
        expected = callback_signature(secret, inp.project_id, inp.doc_id)
        if not hmac.compare_digest(inp.sig, expected):
            raise PermissionError(
                localized_error(
                    "office-editor callback: неверная подпись",
                    "office-editor callback: bad signature",
                )
            )
        token = inp.body.get("token")
        if not token and inp.authorization:
            token = inp.authorization.removeprefix("Bearer ").strip()
        if not token or not isinstance(token, str):
            raise PermissionError(
                localized_error(
                    "office-editor callback: отсутствует JWT",
                    "office-editor callback: missing JWT",
                )
            )
        try:
            office_jwt.verify(token, secret)
        except ValueError as exc:
            raise PermissionError(
                localized_error(
                    f"office-editor callback: недействительный JWT: {exc}",
                    f"office-editor callback: invalid JWT: {exc}",
                )
            ) from exc

    # ── save (status 2 / 6) ─────────────────────────────────────────────────

    async def _save(self, inp: OfficeEditorCallbackInput, key: str) -> None:
        raw_url = inp.body.get("url")
        if not raw_url or not isinstance(raw_url, str):
            raise ValueError(
                localized_error(
                    "office-editor callback: статус сохранения без URL документа",
                    "office-editor callback: save status without a document url",
                )
            )

        # Путь артефакта резолвим заново по проекту и шаблону — данным колбэка
        # путь не доверяем (он приходит от контейнера).
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
        if doc.custom_file is not None:
            output_file = doc.custom_file.stored_path
        else:
            _source_file, output_file = self._template_service.resolve_instance_source(project, doc, version)

        content = await asyncio.to_thread(self._download, self._rewrite_to_published(raw_url))
        await self._put_file_uc.execute(PutFileInput(project_id=inp.project_id, path=output_file, content=content))
        logger.info(
            "office-editor: document saved from DS",
            doc_id=inp.doc_id,
            path=output_file,
            bytes=len(content),
        )
        self._manager.mark_closed(key)
        self._schedule_preview_refresh(project, output_file)

    # ── preview refresh (office-документ → соседний PDF) ────────────────────

    def _schedule_preview_refresh(self, project: Project, output_file: str) -> None:
        """Фоново пересоздать PDF-предпросмотр сохранённого office-документа.

        В фоне, а не в колбэке: холодный старт Gotenberg-контейнера — до
        десятков секунд, а DS ждёт ответа {"error": 0}; затянутый ответ он
        трактует как сбой сохранения. Best-effort, как на сборке: без Docker /
        образа предпросмотр просто остаётся прежним до «Собрать».
        """
        ext = PurePosixPath(output_file).suffix.lower()
        if ext not in CONVERTIBLE_OFFICE_EXTS:
            return
        task = asyncio.get_running_loop().create_task(self._refresh_preview(project, output_file))
        self._preview_tasks.add(task)
        task.add_done_callback(self._preview_tasks.discard)

    async def _refresh_preview(self, project: Project, output_file: str) -> None:
        src_abs = project.folder / output_file
        pdf_abs = src_abs.with_suffix(".pdf")
        try:
            pdf_bytes = await self._convert_manager.convert_to_pdf(
                src_abs, image=resolve_active_office_image(self._settings_repo, "convert")
            )
            if pdf_bytes is None:
                logger.info("office-editor: preview refresh skipped", path=str(src_abs))
                return
            await asyncio.to_thread(pdf_abs.write_bytes, pdf_bytes)
        except Exception as exc:  # noqa: BLE001 — предпросмотр не важнее сохранения
            logger.warning("office-editor: preview refresh failed", path=str(src_abs), exc=str(exc))
            return
        logger.info("office-editor: preview refreshed", path=str(pdf_abs))

    def _rewrite_to_published(self, raw_url: str) -> str:
        """DS отдаёт self-ссылку со своим ВНУТРЕННИМ хостом — мы достаём его
        контейнер только по опубликованному 127.0.0.1:<port>."""
        base = self._manager.base_url
        if base is None:
            return raw_url
        base_parts = urlsplit(base)
        parts = urlsplit(raw_url)
        return urlunsplit((base_parts.scheme, base_parts.netloc, parts.path, parts.query, parts.fragment))

    def _download(self, url: str) -> bytes:
        resp = self._client.get(url, timeout=_DOWNLOAD_TIMEOUT_S)
        if resp.status_code != 200:
            raise RuntimeError(
                localized_error(
                    f"office-editor: не удалось скачать документ, HTTP {resp.status_code}",
                    f"office-editor: document download failed with HTTP {resp.status_code}",
                )
            )
        return resp.content
