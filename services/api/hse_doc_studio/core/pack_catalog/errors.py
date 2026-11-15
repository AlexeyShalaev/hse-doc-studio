"""Ошибки каталогов паков: закрытый список кодов (`contracts/pack-catalog/error_codes.json`) и HTTP-статус.

Тело ответа `{detail, code, ...ctx}`, как у Студии шаблонов. Сбои git источника идут кодами Git-синхронизации
(`contracts/git-sync/error_codes.json`), этот список их не повторяет.
"""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error


class CatalogErrorCode(StrEnum):
    source_not_found = "source_not_found"
    source_busy = "source_busy"
    source_kind_not_allowed = "source_kind_not_allowed"
    source_exists = "source_exists"
    source_disabled = "source_disabled"
    ref_not_found = "ref_not_found"
    packs_path_missing = "packs_path_missing"
    archive_missing = "archive_missing"
    archive_too_large = "archive_too_large"
    archive_invalid = "archive_invalid"
    archive_unsafe = "archive_unsafe"
    tree_too_large = "tree_too_large"
    tree_unsafe = "tree_unsafe"
    inspection_failed = "inspection_failed"
    not_checked = "not_checked"
    revision_moved = "revision_moved"
    plan_blocked = "plan_blocked"
    catalog_busy = "catalog_busy"
    folder_unavailable = "folder_unavailable"
    label_invalid = "label_invalid"


_C = CatalogErrorCode
# Код -> (HTTP-статус, сообщение ru, сообщение en).
_TABLE: dict[CatalogErrorCode, tuple[int, str, str]] = {
    _C.source_not_found: (404, "Источник каталога не найден.", "Catalog source not found."),
    _C.source_busy: (
        409,
        "С этим источником уже идёт проверка или применение. Дождитесь конца.",
        "This source is already being checked or applied. Wait for it to finish.",
    ),
    _C.source_kind_not_allowed: (
        400,
        "Такой вид источника здесь недоступен: папка только в локальной Студии.",
        "This kind of source is not available here: a folder works only in the local Studio.",
    ),
    _C.source_exists: (
        409,
        "Эта папка уже подключена к каталогу.",
        "This folder is already connected to the catalog.",
    ),
    _C.source_disabled: (
        409,
        "Источник выключен. Включите его, чтобы применить новую ревизию.",
        "The source is turned off. Turn it on to apply a new revision.",
    ),
    _C.ref_not_found: (
        404,
        "В репозитории нет такого тега, ветки или коммита.",
        "The repository has no such tag, branch or commit.",
    ),
    _C.packs_path_missing: (
        400,
        "В ревизии нет папки паков по указанному пути.",
        "The revision has no packs folder at the given path.",
    ),
    _C.archive_missing: (
        409,
        "Архив источника не загружен или потерян. Загрузите его снова.",
        "The source archive is not uploaded or was lost. Upload it again.",
    ),
    _C.archive_too_large: (
        413,
        "Архив слишком большой.",
        "The archive is too large.",
    ),
    _C.archive_invalid: (
        400,
        "Не удалось прочитать архив. Нужен .zip или .tar.gz.",
        "Could not read the archive. A .zip or .tar.gz is needed.",
    ),
    _C.archive_unsafe: (
        400,
        "В архиве есть ссылки, абсолютные пути или выход за папку архива. Такой архив не принимается.",
        "The archive has links, absolute paths or paths leaving its folder. Such an archive is refused.",
    ),
    _C.tree_too_large: (
        413,
        "В ревизии слишком много файлов или они слишком большие.",
        "The revision has too many files or they are too large.",
    ),
    _C.tree_unsafe: (
        400,
        "В папке паков есть символьные ссылки. Такие паки не подключаются.",
        "The packs folder has symbolic links. Such packs are not connected.",
    ),
    _C.inspection_failed: (
        422,
        "Не удалось разобрать паки ревизии в отведённое время и память.",
        "Could not read the packs of the revision within the time and memory limits.",
    ),
    _C.not_checked: (
        409,
        "Сначала проверьте источник: применяется только проверенная ревизия.",
        "Check the source first: only a checked revision is applied.",
    ),
    _C.revision_moved: (
        409,
        "Источник изменился после проверки. Проверьте его снова.",
        "The source changed after the check. Check it again.",
    ),
    _C.plan_blocked: (
        409,
        "Применить нельзя: проверка нашла препятствия.",
        "Cannot apply: the check found blockers.",
    ),
    _C.catalog_busy: (
        503,
        "Каталог паков сейчас меняет другой процесс. Повторите чуть позже.",
        "Another process is changing the packs catalog. Try again a bit later.",
    ),
    _C.folder_unavailable: (
        400,
        "Папка недоступна Студии.",
        "The folder is not available to the Studio.",
    ),
    _C.label_invalid: (400, "Название источника слишком длинное.", "The source name is too long."),
}


class CatalogError(Exception):
    """Ошибка каталогов паков с кодом из закрытого списка; `ctx` уходит полями тела ответа."""

    def __init__(self, code: CatalogErrorCode, detail: str | None = None, **ctx: object) -> None:
        status, ru, en = _TABLE[code]
        self.code = code
        self.status = status
        self.detail = detail or localized_error(ru, en)
        self.ctx = ctx
        super().__init__(self.detail)


def status_of(code: CatalogErrorCode) -> int:
    return _TABLE[code][0]
