"""Протокол раннера: конверт задачи и сообщения между API и удалённым раннером.

Все формы замороженные датаклассы из данных, поэтому кодируются `codec.encode` и разбираются
`codec.decode` без отдельного слоя. Транспорт HTTPS JSON под `/api/runner/v1`, раннер сам
забирает работу (pull). Те же формы описаны в `contracts/runner/openapi.yaml`, их сверяет
контрактный тест; менять сначала контракт, затем эту модель и pydantic-схемы.

Любой запрос по задаче несёт `attempt`: завершение с устаревшей попыткой отклоняется
(409 `stale_attempt`), а его выходы игнорируются.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.files import ArtifactRef, ManifestFile

# Версия протокола в пути и в регистрации; несовместимый раннер получает отказ при регистрации.
RUNNER_PROTOCOL_VERSION = 1
RUNNER_API_PREFIX = f"/api/runner/v{RUNNER_PROTOCOL_VERSION}"

# Значения по умолчанию, которые сервер сообщает при регистрации: аренда, пульс и предел долгого опроса.
DEFAULT_LEASE_S = 45
DEFAULT_HEARTBEAT_S = 10
MAX_POLL_WAIT_S = 25


@dataclass(frozen=True)
class JobEnvelope:
    """Всё, что раннер получает на одну попытку задачи.

    `spec` без `local_root`. Актор в спецификации это снимок на момент постановки, а `actor_role`
    роль этого человека в проекте тогда же: применение результата и хуки пересобирают по ним
    актора, а не берут `system_actor`. Манифест полный: у каждого файла есть sha256 и размер.
    """

    spec: JobSpec
    manifest: tuple[ManifestFile, ...]
    timeout_s: float
    attempt: int
    job_token: str
    actor_role: Role | None = None

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise ValueError("attempt starts at 1")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not self.job_token:
            raise ValueError("job_token is empty")
        if self.spec.local_root is not None:
            raise ValueError("local_root does not travel in the envelope")
        for entry in self.manifest:
            if entry.sha256 is None or entry.size is None:
                raise ValueError(f"manifest entry {entry.path!r} needs sha256 and size")


@dataclass(frozen=True)
class RunnerRegisterRequest:
    """Раннер представляется токеном регистрации в заголовке; тело описывает его возможности."""

    name: str
    protocol: int
    version: str
    tags: frozenset[str]
    concurrency: int
    resource_class: str = "standard"

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")


@dataclass(frozen=True)
class RunnerRegisterResponse:
    """`runner_token` показывается один раз: раннер хранит его сам, на сервере остаётся только хеш."""

    runner_id: str
    runner_token: str
    lease_s: int
    heartbeat_s: int
    max_poll_wait_s: int


@dataclass(frozen=True)
class PollRequest:
    """Долгий опрос: сервер держит запрос до `wait_s` и отвечает конвертом или пустотой."""

    wait_s: int
    free_slots: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.wait_s <= MAX_POLL_WAIT_S:
            raise ValueError(f"wait_s must be within 0..{MAX_POLL_WAIT_S}")
        if self.free_slots < 1:
            raise ValueError("free_slots must be at least 1")


@dataclass(frozen=True)
class PollResponse:
    envelope: JobEnvelope | None = None


@dataclass(frozen=True)
class HeartbeatRequest:
    attempt: int


@dataclass(frozen=True)
class HeartbeatResponse:
    """`cancel` доставляет отмену идущей задачи; `lease_until` продлённая аренда."""

    cancel: bool
    lease_until: datetime


@dataclass(frozen=True)
class LogBatch:
    """Порция живого лога; `seq` растёт с нуля, повторная доставка той же порции безвредна."""

    attempt: int
    seq: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class BlobNeedRequest:
    """Какие блобы манифеста раннеру нужны (нет в его кэше)."""

    attempt: int
    sha256: tuple[str, ...]


@dataclass(frozen=True)
class BlobLocation:
    """Где взять блоб: `url` подписанная ссылка хранилища, `None` значит через прокси API."""

    sha256: str
    url: str | None = None


@dataclass(frozen=True)
class BlobNeedResponse:
    blobs: tuple[BlobLocation, ...]


@dataclass(frozen=True)
class ArtifactUploadRequest:
    """Заявка на загрузку выхода; блоб потом уходит по `url` или прямо в API."""

    attempt: int
    artifact: ArtifactRef


@dataclass(frozen=True)
class ArtifactUploadResponse:
    url: str | None = None


@dataclass(frozen=True)
class CompleteRequest:
    """Итог попытки: `result` проводная форма `JobResult` (`encode_result`), выходы уже загружены."""

    attempt: int
    result: dict[str, Any]
    artifacts: tuple[ArtifactRef, ...] = ()


@dataclass(frozen=True)
class CompleteResponse:
    accepted: bool
