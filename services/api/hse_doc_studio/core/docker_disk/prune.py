"""Какие теги образа Студии снять после удачного обновления: старше предыдущей версии.

Одно правило для апдейтера сервера (`infra/update/server_updater/engine.py`) и обновления раннера из админки
(`infra/runner_install/docker_host.py`), storage-cleanup.md, 14.2 (A12, A14, A15). Текущая и предыдущая версии
остаются для отката; теги без номера версии (`latest`, `rollback-prev`, `sha-…`) и версии новее текущей не
трогаются никогда. Чистая функция: что делать с тегами, решает вызывающий (`image rm` без `--force`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from hse_doc_studio.core.update.services import parse_version

# Как «старые версии» локального «Диска»: `X.Y.Z`, можно с `v` и суффиксом предрелиза или сборки.
_VERSION_TAG = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def is_version_tag(tag: str) -> bool:
    return bool(_VERSION_TAG.match(tag))


def stale_version_tags(tags: Iterable[str], *, current: str, previous: str | None) -> list[str]:
    """Номерные теги строго ниже `min(current, previous)`, по возрастанию версии.

    `previous` пуст или не номер версии (прежний контейнер стоял на `latest` или на id образа): что было предыдущим,
    неизвестно, поэтому не снимается ничего. То же, если `current` не номер версии.
    """
    if not previous or not is_version_tag(previous) or not is_version_tag(current):
        return []
    floor = min(parse_version(current), parse_version(previous))
    stale = {tag for tag in tags if is_version_tag(tag) and parse_version(tag) < floor}
    return sorted(stale, key=lambda tag: (parse_version(tag), tag))


def listed_tags(output: str, repo: str) -> list[str]:
    """Теги репозитория `repo` из вывода `docker image ls --format '{{json .}}' <repo>` (строка JSON на образ)."""
    tags: list[str] = []
    for line in output.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("Repository") == repo and isinstance(row.get("Tag"), str):
            tags.append(row["Tag"])
    return tags
