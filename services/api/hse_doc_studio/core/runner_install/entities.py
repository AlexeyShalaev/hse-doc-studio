"""Сущности установки раннера. В них нет секретов: токен живёт только в `LocalRunnerSpec` на время вызова."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from hse_doc_studio.core.runner_install.resources import ResourceOverrides


class InstallTarget(StrEnum):
    docker = "docker"
    kubernetes = "kubernetes"
    ssh = "ssh"


class UnavailableReason(StrEnum):
    """Почему кнопка установки скрыта: интерфейс объясняет это человеку."""

    disabled = "disabled"
    no_socket = "no_socket"
    docker_unreachable = "docker_unreachable"
    not_in_cluster = "not_in_cluster"
    no_permission = "no_permission"


@dataclass(frozen=True, slots=True)
class Capability:
    available: bool
    reason: UnavailableReason | None = None

    @classmethod
    def yes(cls) -> Capability:
        return cls(True)

    @classmethod
    def no(cls, reason: UnavailableReason) -> Capability:
        return cls(False, reason)


class InstallError(Exception):
    """Шаг установки не удался. `code` показывается человеку и переводится, `detail` уже очищен от секретов."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class LocalRunnerSpec:
    name: str
    image: str
    api_url: str
    data_dir: str
    concurrency: int
    token: str = field(repr=False)
    resources: ResourceOverrides | None = None


@dataclass(frozen=True, slots=True)
class LocalInstance:
    """Раннер, поставленный из админки, как его видит хост; `runner_*` это его запись в Студии, если она нашлась."""

    target: InstallTarget
    name: str
    image: str
    state: str
    created_at: datetime | None = None
    runner_id: str | None = None
    runner_version: str | None = None


@dataclass(frozen=True, slots=True)
class PreviousRelease:
    """Какой установка была до обновления: по этому хост возвращает её назад (`ILocalRunnerHost.rollback`).

    `state` принадлежит хосту (spec Deployment, окружение контейнера) и может содержать токен раннера, поэтому не
    попадает ни в repr, ни в задачу, ни в аудит.
    """

    image: str
    state: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class UpgradeOutcome:
    """Итог обновления на месте: какой образ стоял и какой поставлен; `previous` нужен для отката."""

    old_image: str
    new_image: str
    previous: PreviousRelease | None = None


class UpgradeError(InstallError):
    """Обновление не удалось, когда установка уже заменена: `previous` возвращает её к прежней версии."""

    def __init__(self, code: str, detail: str = "", *, previous: PreviousRelease) -> None:
        super().__init__(code, detail)
        self.previous = previous


class InstallStepState(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"


@dataclass(slots=True)
class InstallStep:
    key: str
    state: InstallStepState = InstallStepState.pending
    detail: str = ""


class InstallJobState(StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


@dataclass(slots=True)
class InstallJob:
    """Ход установки: шаги и итог. Хранится в памяти процесса и читается опросом."""

    id: str
    target: InstallTarget
    name: str
    created_by: str
    created_at: datetime
    steps: list[InstallStep]
    state: InstallJobState = InstallJobState.running
    error_code: str | None = None
    error_detail: str = ""
    # Откат неудачного обновления: None, если откатывать было нечего; версия, на которую раннер вернули.
    rolled_back: bool | None = None
    rollback_version: str = ""
    rollback_error: str | None = None

    def step(self, key: str) -> InstallStep:
        for item in self.steps:
            if item.key == key:
                return item
        raise KeyError(key)
