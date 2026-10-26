"""Какие проекты подключили удалённый репозиторий с тем или иным доступом.

Привязка лежит в настройках изолированного хранилища проекта (`[hse] credential = <uuid>` в
`<проект>/.hse-studio/git/config`), а не в project.json: она принадлежит этой машине и вместе с
проектом к коллегам не уезжает. Файл читается как текст, git для этого не запускается: список
доступов открывают часто, а проектов может быть много.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.git_sync.entities import CredentialUsage
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir

logger = structlog.get_logger()

_SECTION = re.compile(r"^\s*\[\s*([A-Za-z0-9.-]+)(?:\s+\"[^\"]*\")?\s*\]\s*(.*)$")
_KEY_VALUE = re.compile(r"^\s*credential\s*=\s*\"?([^\"\s#;]+)\"?\s*(?:[#;].*)?$", re.IGNORECASE)
_MAX_CONFIG_BYTES = 1_000_000


def _hse_credential_value(lines: list[str]) -> str | None:
    in_hse = False
    for line in lines:
        section = _SECTION.match(line)
        if section:
            in_hse = section.group(1).lower() == "hse"
            line = section.group(2)  # noqa: PLW2901 — ключ может стоять на одной строке с секцией
        match = _KEY_VALUE.match(line) if in_hse else None
        if match:
            return match.group(1)
    return None


def read_bound_credential(store_config: Path) -> UUID | None:
    """Значение `hse.credential` из конфига хранилища; None, если файла, ключа или корректного UUID нет."""
    try:
        if store_config.stat().st_size > _MAX_CONFIG_BYTES:
            return None
        lines = store_config.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    value = _hse_credential_value(lines)
    try:
        return None if value is None else UUID(value)
    except ValueError:
        return None


class StoreConfigCredentialUsage:
    def __init__(self, project_index: IProjectIndexRepository, projects: IProjectRepository) -> None:
        self._index = project_index
        self._projects = projects

    def by_credential(self) -> dict[UUID, list[CredentialUsage]]:
        usage: dict[UUID, list[CredentialUsage]] = {}
        for folder in self._index.list_known():
            credential_id = read_bound_credential(store_git_dir(folder) / "config")
            if credential_id is None:
                continue
            try:
                project = self._projects.get(folder)
            except Exception as exc:  # noqa: BLE001 — битый проект не должен ломать список доступов
                logger.warning("credential usage: project is unreadable", folder=str(folder), exc=str(exc))
                continue
            if project is not None:
                usage.setdefault(credential_id, []).append(CredentialUsage(project.id, project.name))
        return usage
