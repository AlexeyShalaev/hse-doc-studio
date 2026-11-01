"""Типы git по HTTPS: сервис протокола, политика приёма push, изменения и нарушения."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

GIT_SCOPES = frozenset({"git:read", "git:write"})
ZERO_SHA = "0" * 40


class GitService(StrEnum):
    upload_pack = "git-upload-pack"
    receive_pack = "git-receive-pack"


class PushViolationCode(StrEnum):
    ref_forbidden = "ref_forbidden"
    not_fast_forward = "not_fast_forward"
    path_outside_scope = "path_outside_scope"
    unsafe_path = "unsafe_path"
    symlink = "symlink"
    submodule = "submodule"
    large_file = "large_file"
    schema_newer = "schema_newer"
    service_dir = "service_dir"


@dataclass(frozen=True)
class PushPolicy:
    """Что можно отправить в проект: ветка стора, область записи автора и пределы.

    `scope == "all"` у владельца, у права `can_edit_all` и в solo-проекте; иначе первые сегменты путей, куда
    автору можно писать (своя папка и `shared`, если общие документы включены). Совместимость схемы:
    номер схемы данных Студии сервера; `project.json` с требованиями выше отвергается.
    """

    branch: str
    team: bool
    shared_enabled: bool
    scope: Literal["all"] | tuple[str, ...]
    max_blob_bytes: int
    studio_read_compat: int
    studio_write_compat: int

    @property
    def owner_or_all(self) -> bool:
        return self.scope == "all"


@dataclass(frozen=True)
class PushChange:
    """Одна строка итоговой разницы `old..new` (без переименований); у удаления режима и размера нет."""

    status: Literal["A", "M", "D", "T"]
    path: str
    mode: str | None
    size: int | None


@dataclass(frozen=True)
class PushViolation:
    code: PushViolationCode
    path: str | None
