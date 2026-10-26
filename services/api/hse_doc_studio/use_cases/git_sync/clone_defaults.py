from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')
_SPACES = re.compile(r"\s+")
_MAX_NAME = 64
_MAX_ATTEMPTS = 1000
_FALLBACK = "project"


@dataclass
class CloneDefaultsInput:
    name: str | None = None


class GetCloneDefaultsUC:
    """Папка по умолчанию для клонирования: свободное имя под каталогом проектов."""

    def __init__(self, default_projects_dir: Path) -> None:
        self._root = default_projects_dir

    async def execute(self, inp: CloneDefaultsInput) -> Path:
        return await asyncio.to_thread(self._pick, folder_name(inp.name))

    def _pick(self, name: str) -> Path:
        candidate = self._root / name
        for attempt in range(2, _MAX_ATTEMPTS):
            if not candidate.exists():
                break
            candidate = self._root / f"{name}-{attempt}"
        return candidate


def folder_name(name: str | None) -> str:
    """Имя папки из названия проекта или репозитория: без служебных символов ФС, русские буквы остаются."""
    cleaned = _UNSAFE.sub(" ", name or "")
    cleaned = _SPACES.sub("-", cleaned.strip()).strip(".-")[:_MAX_NAME].rstrip(".-")
    return cleaned or _FALLBACK
