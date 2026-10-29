"""Настройки процесса раннера (HSE_RUNNER__*): отдельно от настроек api, раннеру база и тома не нужны."""

from __future__ import annotations

import socket
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_GIB = 1024**3


class RunnerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HSE_RUNNER__", env_nested_delimiter="__", extra="ignore", case_sensitive=False
    )

    api_url: str = Field(description="Адрес api Студии, например https://studio.example.org.")
    token: SecretStr = Field(
        description=(
            "Токен регистрации из админки: нужен один раз. Выданный раннеру токен хранится в data_dir/identity.json, "
            "после этого значение можно убрать из окружения."
        )
    )
    name: str = Field(default_factory=socket.gethostname, description="Имя раннера в списке администратора.")
    tags: str = Field(
        default="",
        description="Теги через запятую; пусто значит определить по окружению (verify, pack, office, archive:*).",
    )
    concurrency: int = Field(default=1, ge=1, le=64, description="Сколько задач раннер ведёт одновременно.")
    data_dir: Path = Field(
        default=Path.home() / ".local" / "share" / "hse-runner",
        description="Рабочие папки проектов и кэш блобов.",
    )
    office_url: str | None = Field(
        default=None,
        description="Адрес Gotenberg для office.convert; без него раннер не берёт задачи конвертации.",
    )
    office_timeout_s: float = Field(default=180.0, gt=0, description="Предел одной конвертации.")
    cache_max_bytes: int = Field(default=2 * _GIB, gt=0, description="Предел кэша блобов; лишнее вытесняется по LRU.")
    poll_wait_s: int = Field(default=25, ge=0, le=25, description="Длительность долгого опроса.")

    def explicit_tags(self) -> frozenset[str] | None:
        tags = frozenset(part.strip() for part in self.tags.split(",") if part.strip())
        return tags or None
