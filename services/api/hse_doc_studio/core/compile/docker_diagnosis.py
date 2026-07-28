"""Разбор причины, по которой докер недоступен, — в машиночитаемый код.

Сырой stderr докера («permission denied while trying to connect to the Docker
daemon socket at unix:///var/run/docker.sock…») пользователю ничего не говорит:
он видит красный блок и не знает, что делать. Классифицируем ответ здесь, в
домене, чтобы и настройки, и триггер сборки показывали ОДНУ причину, а тексты и
команду-подсказку рисовал фронтенд по коду (тексты живут в i18n-словарях).

Отдельный код у нехватки прав неслучаен: это единственная причина, которую
пользователь чинит не в докере, а в СВОЁМ compose-файле, и починка полностью
детерминирована — нужен gid владельца сокета.
"""

from __future__ import annotations

from enum import StrEnum


class DockerUnavailableReason(StrEnum):
    """Почему `docker version` не отработал."""

    CLI_MISSING = "cli_missing"
    """Бинарника `docker` нет в PATH — образ собран без него или запуск не в контейнере."""

    SOCKET_PERMISSION = "socket_permission"
    """Сокет виден, но процессу не хватает прав на него (нужна группа-владелец)."""

    DAEMON_UNREACHABLE = "daemon_unreachable"
    """Сокет не отвечает: демон не запущен или не проброшен в контейнер."""

    TIMEOUT = "timeout"
    """Демон не ответил за отведённое время."""


_PERMISSION_MARKERS = (
    "permission denied",
    "got permission denied",
)
_SOCKET_MARKERS = (
    "docker.sock",
    "docker daemon socket",
)


def classify_docker_error(stderr: str) -> DockerUnavailableReason:
    """Классифицировать stderr неудачного `docker version`."""
    text = stderr.lower()
    if "permission denied" in text and any(m in text for m in _SOCKET_MARKERS):
        return DockerUnavailableReason.SOCKET_PERMISSION
    # Сокета может не быть в сообщении, если докер сослался только на права:
    # это всё равно про доступ, а не про мёртвый демон.
    if any(m in text for m in _PERMISSION_MARKERS):
        return DockerUnavailableReason.SOCKET_PERMISSION
    return DockerUnavailableReason.DAEMON_UNREACHABLE


class MountFailureReason(StrEnum):
    """Почему демон не смог смонтировать каталог хоста.

    Отдельная шкала от `DockerUnavailableReason`: живой демон — необходимое, но
    недостаточное условие. Между хостом и демоном на Windows и macOS стоит
    виртуальная машина Docker Desktop со своим списком расшаренных каталогов, и
    папка вне этого списка даёт не ошибку приложения, а ПУСТОЙ маунт. Внутри
    пустого `/work` latexmk честно сообщает «Could not find file» и выходит с
    кодом 11 — сообщение, по которому невозможно догадаться, что дело в
    настройках Docker Desktop.
    """

    NOT_SHARED = "not_shared"
    """Каталог вне списка file sharing у Docker Desktop — пользователь добавляет его в настройках докера."""

    PERMISSION = "permission"
    """Демон видит каталог, но не имеет права его читать."""

    MOUNT_REJECTED = "mount_rejected"
    """Демон отказал в монтировании по иной причине — показываем его текст как есть."""


_NOT_SHARED_MARKERS = (
    "not shared from the host",
    "drive is not shared",
    "is not shared from os x",
    "filesharing",
    "file sharing",
)
_MOUNT_MARKERS = (
    "mounts denied",
    "invalid mount",
    "cannot start service",
    "error while creating mount source path",
    "bind source path does not exist",
)


def classify_mount_error(stderr: str) -> MountFailureReason:
    """Классифицировать stderr неудачного `docker run -v <путь>:...`."""
    text = stderr.lower()
    if any(m in text for m in _NOT_SHARED_MARKERS):
        return MountFailureReason.NOT_SHARED
    if any(m in text for m in _PERMISSION_MARKERS):
        return MountFailureReason.PERMISSION
    if any(m in text for m in _MOUNT_MARKERS):
        return MountFailureReason.MOUNT_REJECTED
    return MountFailureReason.MOUNT_REJECTED
