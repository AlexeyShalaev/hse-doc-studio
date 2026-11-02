from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UpdaterConfig:
    api_url: str
    token: str
    data_dir: Path
    services: tuple[str, ...] = ("api", "runner")  # порядок запуска; остановка в обратном
    project: str = ""  # проект compose; пусто значит взять с контейнера api по метке
    snapshot_volume: str = ""  # том данных апдейтера; пусто значит найти по собственному контейнеру
    env_file: Path | None = None  # .env установки: после успеха в нём обновляется TAG
    health_url: str = ""
    health_token: str = ""
    poll_s: float = 15.0
    heartbeat_s: float = 30.0
    health_timeout_s: float = 300.0
    stable_s: float = 20.0
    stop_timeout_s: int = 60
    pull_timeout_s: float = 1800.0
    migrate_timeout_s: float = 3600.0
    min_free_bytes: int = 1024**3
    keep_snapshots: int = 2
    version: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, version: str = "") -> UpdaterConfig:
        e = env if env is not None else dict(os.environ)
        token = e.get("HSE_UPDATER__TOKEN", "").strip()
        if not token:
            msg = "HSE_UPDATER__TOKEN is not set"
            raise ValueError(msg)
        api_url = e.get("HSE_UPDATER__API_URL", "http://api:8000")
        env_file = e.get("HSE_UPDATER__ENV_FILE", "").strip()
        return cls(
            api_url=api_url,
            token=token,
            data_dir=Path(e.get("HSE_UPDATER__DATA_DIR", "/var/lib/hse-updater")),
            services=tuple(s.strip() for s in e.get("HSE_UPDATER__SERVICES", "api,runner").split(",") if s.strip()),
            project=e.get("HSE_UPDATER__PROJECT", ""),
            snapshot_volume=e.get("HSE_UPDATER__SNAPSHOT_VOLUME", ""),
            env_file=Path(env_file) if env_file else None,
            health_url=e.get("HSE_UPDATER__HEALTH_URL", api_url.rstrip("/") + "/health/ready"),
            health_token=e.get("HSE_UPDATER__HEALTH_TOKEN", ""),
            poll_s=float(e.get("HSE_UPDATER__POLL_S", "15")),
            health_timeout_s=float(e.get("HSE_UPDATER__HEALTH_TIMEOUT_S", "300")),
            version=version,
        )
