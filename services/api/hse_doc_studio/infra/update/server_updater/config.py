from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KubeSettings:
    """Исполнитель kubernetes (HSE_UPDATER__EXECUTOR=kubernetes): какой Deployment и как долго ждать."""

    deployment: str
    namespace: str = ""  # пусто значит namespace ServiceAccount пода апдейтера
    container: str = "api"
    api_url: str = ""
    poll_s: float = 2.0
    stop_timeout_s: float = 180.0
    migrate_timeout_s: float = 3600.0
    probe_job_timeout_s: float = 300.0  # `db current`, cosign
    pod_start_timeout_s: float = 300.0  # pull образа
    job_ttl_s: int = 86400

    @classmethod
    def from_env(cls, e: dict[str, str]) -> KubeSettings:
        deployment = e.get("HSE_UPDATER__KUBE__DEPLOYMENT", "").strip()
        if not deployment:
            msg = "HSE_UPDATER__KUBE__DEPLOYMENT is not set"
            raise ValueError(msg)
        return cls(
            deployment=deployment,
            namespace=e.get("HSE_UPDATER__KUBE__NAMESPACE", "").strip(),
            container=e.get("HSE_UPDATER__KUBE__CONTAINER", "api").strip() or "api",
            api_url=e.get("HSE_UPDATER__KUBE__API_URL", "").strip(),
            stop_timeout_s=float(e.get("HSE_UPDATER__KUBE__STOP_TIMEOUT_S", "180")),
            migrate_timeout_s=float(e.get("HSE_UPDATER__KUBE__MIGRATE_TIMEOUT_S", "3600")),
            pod_start_timeout_s=float(e.get("HSE_UPDATER__KUBE__POD_START_TIMEOUT_S", "300")),
        )


_OFF = frozenset({"0", "false", "no", "off"})


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
    # После удачного обновления снять теги образа Студии ниже предыдущей версии (storage-cleanup.md, 14.7).
    prune_old_images: bool = True
    version: str = ""
    kube: KubeSettings | None = None  # задан значит исполнитель kubernetes, иначе compose

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, version: str = "") -> UpdaterConfig:
        e = env if env is not None else dict(os.environ)
        token = e.get("HSE_UPDATER__TOKEN", "").strip()
        if not token:
            msg = "HSE_UPDATER__TOKEN is not set"
            raise ValueError(msg)
        api_url = e.get("HSE_UPDATER__API_URL", "http://api:8000")
        kube = KubeSettings.from_env(e) if e.get("HSE_UPDATER__EXECUTOR", "compose") == "kubernetes" else None
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
            prune_old_images=e.get("HSE_UPDATER__PRUNE_OLD_IMAGES", "true").strip().lower() not in _OFF,
            version=version,
            kube=kube,
        )
