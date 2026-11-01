"""Команды переноса из локальной Студии на сервер: `hse-doc-studio server import` и `server import-project`.

Оператор запускает их на сервере от имени пользователя (по e-mail): записи принадлежат ему так же,
как если бы он перенёс их сам. Сама логика живёт в сценариях, здесь только актор, чтение входа и отчёт.
"""

from __future__ import annotations

import os
import stat
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.projects.importer import ImportReport
from hse_doc_studio.use_cases.projects.import_project import ImportProjectInput, ImportProjectUC
from hse_doc_studio.use_cases.server_import.import_user_data import (
    ImportNoteCode,
    ImportUserDataInput,
    ImportUserDataReport,
    ImportUserDataUC,
)

if TYPE_CHECKING:
    from dishka import AsyncContainer

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


class ImportCliError(Exception):
    """Ошибка ввода оператора: нет такого пользователя, каталога или архива."""


async def _actor_of(container: AsyncContainer, email: str) -> Actor:
    async with container() as request:
        users = await request.get(IUserRepository)
        user = await users.get_by_email(email)
    if user is None:
        raise ImportCliError(f"пользователь {email} не найден")
    if not user.can_sign_in:
        raise ImportCliError(f"учётная запись {email} не активна")
    return Actor.user(
        user.id, name=user.name, email=user.email, is_instance_admin=user.is_instance_admin, source=ActorSource.job
    )


async def import_user_data(
    container: AsyncContainer, *, email: str, data_dir: Path, dry_run: bool, include_instance: bool
) -> ImportUserDataReport:
    if not data_dir.is_dir():
        raise ImportCliError(f"каталог данных не найден: {data_dir}")
    actor = await _actor_of(container, email)
    set_current_actor(actor)
    try:
        async with container() as request:
            uc = await request.get(ImportUserDataUC)
            return await uc.execute(
                ImportUserDataInput(data_dir=data_dir, dry_run=dry_run, include_instance=include_instance)
            )
    finally:
        set_current_actor(None)


def format_data_report(report: ImportUserDataReport, write: Callable[[str], None]) -> None:
    mode = "пробный запуск, ничего не записано" if report.dry_run else "готово"
    write(f"перенос данных: {mode}")
    verb = "будет создано" if report.dry_run else "создано"
    write(f"  настройки: {verb} {report.settings_created}, уже были на сервере {report.settings_kept}")
    write(f"  ИИ-провайдеры: {verb} {report.providers_created}, уже были на сервере {report.providers_kept}")
    for note in report.notes:
        write(f"  {_note_text(note.code, note.subject, note.detail)}")


def _note_text(code: ImportNoteCode, subject: str, detail: str) -> str:
    match code:
        case ImportNoteCode.unreadable:
            return f"предупреждение: не удалось прочитать {subject}"
        case ImportNoteCode.invalid_setting:
            return f"предупреждение: настройка {subject} с недопустимым значением пропущена"
        case ImportNoteCode.instance_setting_skipped:
            return f"пропущено: {subject} это настройка всей установки (нужен флаг --include-instance)"
        case ImportNoteCode.provider_failed:
            return f"ошибка: ИИ-провайдер {subject} не перенесён: {detail}"
        case ImportNoteCode.not_transferred:
            return f"не переносится: {subject}, добавьте на сервере заново"


def zip_folder(folder: Path, target: Path) -> None:
    """Папка проекта в zip для приёма. Символьные ссылки не упаковываются: приём всё равно отверг бы их."""
    if not folder.is_dir():
        raise ImportCliError(f"папка проекта не найдена: {folder}")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for current, dirs, files in os.walk(folder, followlinks=False):
            here = Path(current)
            for name in [*dirs, *files]:
                if stat.S_ISLNK(os.lstat(here / name).st_mode):
                    raise ImportCliError(f"в папке есть символьная ссылка: {(here / name).relative_to(folder)}")
            for name in files:
                path = here / name
                zf.write(path, path.relative_to(folder).as_posix())


async def import_project(container: AsyncContainer, *, email: str, source: Path, dry_run: bool) -> ImportReport | None:
    """None при пробном запуске: проверка архива прошла, на том ничего не положено."""
    if not source.exists():
        raise ImportCliError(f"не найдено: {source}")
    actor = await _actor_of(container, email)
    set_current_actor(actor)
    try:
        with tempfile.TemporaryDirectory(prefix="hse-import-") as scratch:
            archive = source
            if source.is_dir():
                archive = Path(scratch) / "project.zip"
                zip_folder(source, archive)
            async with container() as request:
                uc = await request.get(ImportProjectUC)
                if dry_run:
                    await uc.check(archive)
                    return None
                return await uc.execute(ImportProjectInput(archive=archive))
    finally:
        set_current_actor(None)


def format_project_report(report: ImportReport | None, write: Callable[[str], None]) -> None:
    if report is None:
        write("перенос проекта: пробный запуск, архив принят бы, ничего не записано")
        return
    write(f"проект перенесён: {report.name} ({report.project_id})")
    write(f"  файлов: {report.files}, чатов: {report.chats}")
    if report.id_regenerated:
        write("  id проекта занят, выдан новый")
    for warning in report.warnings:
        write(f"  предупреждение: {warning.code.value} {warning.detail}".rstrip())
