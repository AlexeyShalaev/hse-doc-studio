"""Сущности Студии шаблонов: рабочее пространство, выпущенные версии, дерево паков, право раздела.

Рабочее пространство это пара «откуда и куда» (docs/design/template-studio.md, 4.1): git-репозиторий паков
(частичный клон в `data_dir/pack-studio/workspaces/<id>`) или папка на диске (только локально).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.pack_studio.paths import fold_path, template_key, version_ref_of


class WorkspaceKind(StrEnum):
    git = "git"
    folder = "folder"


class WorkspaceState(StrEnum):
    """`cloning`: клон идёт в фоне; `ready`: файлы доступны; `failed`: клон не удался (`error`)."""

    cloning = "cloning"
    ready = "ready"
    failed = "failed"


@dataclass(frozen=True)
class WorkspaceError:
    """Код из `contracts/pack-studio/error_codes.json` или `contracts/git-sync/error_codes.json` и текст."""

    code: str
    detail: str


@dataclass(frozen=True)
class PackWorkspace:
    id: UUID
    owner_id: str | None
    kind: WorkspaceKind
    label: str
    # Папка паков внутри репозитория или папки: `packs`, `.` (корень).
    packs_path: str
    created_at: datetime
    updated_at: datetime
    state: WorkspaceState = WorkspaceState.ready
    # git: адрес без секретов (как `RemoteUrl.display_url`), доступ по id, явное согласие на открытый http.
    remote_url: str | None = None
    credential_id: UUID | None = None
    insecure_http: bool = False
    # git: базовая ветка (по умолчанию HEAD сервера) и её вершина после последней выборки.
    base_branch: str | None = None
    base_sha: str | None = None
    fetched_at: datetime | None = None
    # git: рабочая ветка появляется с первым коммитом (срез T6), до этого дерево стоит на вершине базы.
    work_branch: str | None = None
    # git: запрос на слияние и последний статус проверок хостинга (срез T6).
    pr_url: str | None = None
    pr_number: int | None = None
    ci_status: str | None = None
    # folder: абсолютный путь папки в файловой системе Студии (контейнерный, если Студия в Docker).
    folder: str | None = None
    error: WorkspaceError | None = None


@dataclass(frozen=True)
class ReleasedVersions:
    """Выпущенные версии по шаблонам: `<пак>/<шаблон>` (свёрнутый регистр) -> версия -> дайджест каталога.

    Источник (D10): реестры `releases.yaml` базовой ветки после выборки у git, реестры на диске у папки.
    `sha` это вершина базы, с которой снят список (у папки None).
    """

    templates: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    sha: str | None = None

    def digest(self, pack: str, template: str, version: str) -> str | None:
        versions = self.templates.get(template_key(pack, template), {})
        folded = fold_path(version)
        return next((digest for v, digest in versions.items() if fold_path(v) == folded), None)

    def is_released(self, pack: str, template: str, version: str) -> bool:
        return self.digest(pack, template, version) is not None

    def released_dir_of(self, path: str) -> str | None:
        """Каталог выпущенной версии, внутри которого лежит путь (или который он и есть); иначе None."""
        ref = version_ref_of(path)
        if ref is None or not self.is_released(ref.pack, ref.template, ref.version):
            return None
        return ref.dir


@dataclass(frozen=True)
class TreeVersion:
    version: str
    path: str
    status: str | None
    released: bool
    # Каталог выпущенной версии отличается от дайджеста в реестре: его правили мимо Студии (7.3).
    modified: bool


@dataclass(frozen=True)
class TreeTemplate:
    id: str
    path: str
    name: Mapping[str, str] | None
    default_version: str | None
    versions: tuple[TreeVersion, ...]


@dataclass(frozen=True)
class TreePack:
    id: str
    path: str
    name: Mapping[str, str] | None
    templates: tuple[TreeTemplate, ...]


@dataclass(frozen=True)
class TreeFile:
    path: str
    is_dir: bool
    size: int
    # Почему файл нельзя менять через Студию: `version_released` или `releases_read_only`; None: можно.
    read_only: str | None = None


@dataclass(frozen=True)
class PackTree:
    packs: tuple[TreePack, ...]
    files: tuple[TreeFile, ...]
    truncated: bool = False


class GrantSubjectKind(StrEnum):
    user = "user"
    group = "group"


@dataclass(frozen=True)
class PackStudioGrant:
    """Право «Автор шаблонов» человеку или группе организации (только сервер)."""

    id: UUID
    subject: GrantSubjectKind
    subject_id: str
    created_at: datetime
    granted_by: str | None = None
    # Подписи для админки: имя и почта человека, название группы и её организации.
    name: str | None = None
    email: str | None = None
    org_slug: str | None = None
    org_name: str | None = None


@dataclass(frozen=True)
class SectionState:
    """Включён ли раздел и задан ли он окружением (тогда переключатель в интерфейсе только для чтения)."""

    enabled: bool
    locked: bool
