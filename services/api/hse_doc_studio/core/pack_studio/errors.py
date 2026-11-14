"""Ошибки Студии шаблонов: закрытый список кодов (`contracts/pack-studio/error_codes.json`) и HTTP-статус каждого.

Тело ответа `{detail, code, ...ctx}`: `detail` уже на языке интерфейса, `ctx` несёт поля для окна на месте
(ETag и текст файла при `stale_file`, путь при `version_released`). Сбои git рабочего пространства идут кодами
Git-синхронизации (`contracts/git-sync/error_codes.json`), этот список их не повторяет.
"""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error


class PackStudioErrorCode(StrEnum):
    # Раздел и права (D4)
    pack_studio_disabled = "pack_studio_disabled"
    pack_studio_forbidden = "pack_studio_forbidden"
    pack_scope_required = "pack_scope_required"
    # Рабочие пространства (4.1)
    workspace_not_found = "workspace_not_found"
    workspace_not_ready = "workspace_not_ready"
    workspace_busy = "workspace_busy"
    workspace_limit = "workspace_limit"
    workspace_too_large = "workspace_too_large"
    workspace_interrupted = "workspace_interrupted"
    folder_not_allowed = "folder_not_allowed"
    folder_unavailable = "folder_unavailable"
    not_a_git_workspace = "not_a_git_workspace"
    not_a_pack_repo = "not_a_pack_repo"
    # Файлы (4.5, раздел 9)
    file_not_found = "file_not_found"
    path_not_allowed = "path_not_allowed"
    file_too_large = "file_too_large"
    stale_file = "stale_file"
    version_released = "version_released"
    releases_read_only = "releases_read_only"
    not_yaml = "not_yaml"
    yaml_patch_conflict = "yaml_patch_conflict"
    # Права раздела в админке
    grant_subject_not_found = "grant_subject_not_found"
    grant_exists = "grant_exists"
    grant_not_found = "grant_not_found"
    section_locked = "section_locked"
    # Следующие срезы (T6, T7, T10, T15): коды заняты заранее, чтобы контракт рос только дописыванием
    pack_id_taken = "pack_id_taken"
    push_denied = "push_denied"
    pr_permission_missing = "pr_permission_missing"
    fork_required = "fork_required"
    ci_status_unavailable = "ci_status_unavailable"
    lint_failed = "lint_failed"
    class_softer_than_changes = "class_softer_than_changes"
    preview_quota = "preview_quota"


_C = PackStudioErrorCode

# Код -> (HTTP-статус, сообщение ru, сообщение en).
_TABLE: dict[PackStudioErrorCode, tuple[int, str, str]] = {
    _C.pack_studio_disabled: (404, "Студия шаблонов выключена.", "The Pack Studio is turned off."),
    _C.pack_studio_forbidden: (
        403,
        "Нет права «Автор шаблонов». Его выдаёт администратор установки.",
        "You do not have the Pack author right. The instance administrator grants it.",
    ),
    _C.pack_scope_required: (
        403,
        "Токену доступа нужна область packs.",
        "The access token needs the packs scope.",
    ),
    _C.workspace_not_found: (404, "Рабочее пространство не найдено.", "Workspace not found."),
    _C.workspace_not_ready: (
        409,
        "Рабочее пространство ещё не готово: репозиторий скачивается или скачать его не удалось.",
        "The workspace is not ready: the repository is still downloading or the download failed.",
    ),
    _C.workspace_busy: (
        409,
        "С рабочим пространством уже идёт операция. Дождитесь её конца.",
        "An operation is already running on this workspace. Wait for it to finish.",
    ),
    _C.workspace_limit: (
        409,
        "Рабочих пространств слишком много. Удалите ненужные.",
        "Too many workspaces. Delete the ones you no longer need.",
    ),
    _C.workspace_too_large: (
        413,
        "Репозиторий паков слишком большой для Студии шаблонов.",
        "The packs repository is too large for the Pack Studio.",
    ),
    _C.workspace_interrupted: (
        409,
        "Скачивание репозитория прервалось. Обновите рабочее пространство, чтобы начать заново.",
        "The repository download was interrupted. Refresh the workspace to start again.",
    ),
    _C.folder_not_allowed: (
        403,
        "Папку на диске можно открыть только в локальной Студии.",
        "A folder on disk can only be opened in a local Studio.",
    ),
    _C.folder_unavailable: (
        400,
        "Папка не найдена или Студии к ней нет доступа.",
        "The folder does not exist or the Studio cannot access it.",
    ),
    _C.not_a_git_workspace: (
        409,
        "Это рабочее пространство над папкой, у него нет git.",
        "This workspace is a folder, it has no git.",
    ),
    _C.not_a_pack_repo: (
        400,
        "В папке паков нет ни одного пака (pack.yaml), и она не пуста.",
        "The packs folder has no pack (pack.yaml) and is not empty.",
    ),
    _C.file_not_found: (404, "Файл не найден.", "File not found."),
    _C.path_not_allowed: (
        400,
        "Недопустимый путь: только внутри папки паков, без «..», ссылок и служебных папок git.",
        "Invalid path: only inside the packs folder, without '..', links or git folders.",
    ),
    _C.file_too_large: (413, "Файл слишком большой.", "The file is too large."),
    _C.stale_file: (
        409,
        "Файл изменился с тех пор, как вы его открыли.",
        "The file has changed since you opened it.",
    ),
    _C.version_released: (
        409,
        "Эта версия шаблона выпущена, её файлы менять нельзя. Создайте новую версию.",
        "This template version is released, its files cannot change. Create a new version.",
    ),
    _C.releases_read_only: (
        409,
        "Реестр выпусков меняет только мастер «Новая версия».",
        "Only the New version wizard changes the release registry.",
    ),
    _C.not_yaml: (400, "Точечные правки возможны только в файлах YAML.", "Point edits only work on YAML files."),
    _C.yaml_patch_conflict: (
        409,
        "Правку нельзя применить к текущему тексту файла.",
        "The edit cannot be applied to the current text of the file.",
    ),
    _C.grant_subject_not_found: (404, "Человек или группа не найдены.", "Person or group not found."),
    _C.grant_exists: (409, "Право уже выдано.", "The right is already granted."),
    _C.grant_not_found: (404, "Право не найдено.", "Grant not found."),
    _C.section_locked: (
        409,
        "Раздел включается переменной окружения HSE_STUDIO__PACK_STUDIO__ENABLED.",
        "The section is set by the HSE_STUDIO__PACK_STUDIO__ENABLED environment variable.",
    ),
    _C.pack_id_taken: (409, "Пак с таким id уже есть.", "A pack with this id already exists."),
    _C.push_denied: (403, "Нет права отправлять в этот репозиторий.", "You cannot push to this repository."),
    _C.pr_permission_missing: (
        403,
        "Токену не хватает прав, чтобы открыть запрос на слияние.",
        "The token lacks the rights to open a pull request.",
    ),
    _C.fork_required: (409, "Нужен форк репозитория.", "A fork of the repository is required."),
    _C.ci_status_unavailable: (
        409,
        "Статус проверок хостинга недоступен.",
        "The hosting checks status is unavailable.",
    ),
    _C.lint_failed: (409, "Пак не прошёл проверку.", "The pack did not pass the checks."),
    _C.class_softer_than_changes: (
        409,
        "Номер версии мягче, чем требуют изменения.",
        "The version number is softer than the changes require.",
    ),
    _C.preview_quota: (429, "Слишком много сборок предпросмотра.", "Too many preview builds."),
}


class PackStudioError(Exception):
    """Ошибка Студии шаблонов с кодом из закрытого списка; `ctx` уходит полями тела ответа."""

    def __init__(self, code: PackStudioErrorCode, detail: str | None = None, **ctx: object) -> None:
        status, ru, en = _TABLE[code]
        self.code = code
        self.status = status
        self.detail = detail or localized_error(ru, en)
        self.ctx = ctx
        super().__init__(self.detail)


def status_of(code: PackStudioErrorCode) -> int:
    return _TABLE[code][0]
