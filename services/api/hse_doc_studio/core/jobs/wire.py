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
from hse_doc_studio.core.jobs.relay import (
    ENDPOINT_NAME_RE,
    MAX_AI_ENDPOINTS,
    RELAY_MAX_EVENTS_PER_BATCH,
    RelayEventKind,
)
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, RunnerHostKind, RunnerOwnerKind

# Версия протокола в пути и в регистрации; несовместимый раннер получает отказ при регистрации.
RUNNER_PROTOCOL_VERSION = 1
RUNNER_API_PREFIX = f"/api/runner/v{RUNNER_PROTOCOL_VERSION}"

# Значения по умолчанию, которые сервер сообщает при регистрации: аренда, пульс и предел долгого опроса.
DEFAULT_LEASE_S = 45
DEFAULT_HEARTBEAT_S = 10
MAX_POLL_WAIT_S = 25

# Возможности протокола сверх версии 1. Сервер шлёт раннеру новое (вид `ai.relay`, поля) только после того,
# как раннер объявил соответствующую возможность в `/announce`; старый раннер работает как раньше.
FEATURE_ANNOUNCE = "announce"
FEATURE_OFFLINE = "offline"
FEATURE_AI_SLOTS = "ai_slots"
FEATURE_AI_RELAY = "ai_relay"
SERVER_FEATURES = frozenset({FEATURE_ANNOUNCE, FEATURE_OFFLINE, FEATURE_AI_SLOTS, FEATURE_AI_RELAY})


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
    # Свободные слоты ретрансляции ИИ; шлёт только раннер с возможностью `ai_slots`.
    free_ai_slots: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.wait_s <= MAX_POLL_WAIT_S:
            raise ValueError(f"wait_s must be within 0..{MAX_POLL_WAIT_S}")
        if self.free_slots < 0 or self.free_ai_slots < 0:
            raise ValueError("free slots cannot be negative")
        if self.free_slots + self.free_ai_slots < 1:
            raise ValueError("a poll needs at least one free slot")


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


def _check_endpoints(endpoints: tuple[DeclaredAiEndpoint, ...]) -> None:
    if len(endpoints) > MAX_AI_ENDPOINTS:
        raise ValueError(f"at most {MAX_AI_ENDPOINTS} ai endpoints")
    names = [endpoint.name for endpoint in endpoints]
    if len(set(names)) != len(names):
        raise ValueError("ai endpoint names must be unique")
    for name in names:
        if not ENDPOINT_NAME_RE.match(name):
            raise ValueError(f"bad ai endpoint name {name!r}")


@dataclass(frozen=True)
class RunnerAnnounceRequest:
    """Возможности и описание раннера; `name=None` не меняет имя (имя из интерфейса хозяина важнее)."""

    name: str | None
    version: str
    tags: frozenset[str]
    concurrency: int
    ai_concurrency: int
    host_kind: RunnerHostKind
    # Неизвестные серверу возможности он молча отбрасывает.
    features: frozenset[str]
    ai_endpoints: tuple[DeclaredAiEndpoint, ...]

    def __post_init__(self) -> None:
        if self.concurrency < 1 or self.ai_concurrency < 0:
            raise ValueError("concurrency must be at least 1, ai_concurrency non-negative")
        _check_endpoints(self.ai_endpoints)


@dataclass(frozen=True)
class RunnerAnnounceResponse:
    runner_id: str
    # Пересечение возможностей раннера и сервера.
    server_features: frozenset[str]
    owner_kind: RunnerOwnerKind
    paused: bool
    # Как часто слать пульс задачи ретрансляции, пока порций нет.
    relay_keepalive_s: int


@dataclass(frozen=True)
class RunnerPairStartRequest:
    name: str
    host_kind: RunnerHostKind

    def __post_init__(self) -> None:
        if not 1 <= len(self.name) <= 128:  # noqa: PLR2004
            raise ValueError("name must be 1..128 characters")


@dataclass(frozen=True)
class RunnerPairStartResponse:
    """`device_code` секрет устройства; `user_code` человек подтверждает на сайте."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class RunnerPairPollRequest:
    device_code: str


@dataclass(frozen=True)
class RunnerPairPollResponse:
    """`registration_token` непуст ровно один раз, при `approved`."""

    status: str
    registration_token: str | None = None


@dataclass(frozen=True)
class RelayEvent:
    kind: RelayEventKind
    status: int | None = None
    content_type: str | None = None
    # base64; декодированный размер до 64 KiB.
    data: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class RelayEventBatch:
    """Порция событий ответа модели; `seq` растёт с нуля на попытку, повтор той же порции безвреден."""

    attempt: int
    seq: int
    events: tuple[RelayEvent, ...]

    def __post_init__(self) -> None:
        if self.attempt < 1 or self.seq < 0:
            raise ValueError("attempt starts at 1, seq at 0")
        if not 1 <= len(self.events) <= RELAY_MAX_EVENTS_PER_BATCH:
            raise ValueError(f"a batch carries 1..{RELAY_MAX_EVENTS_PER_BATCH} events")


@dataclass(frozen=True)
class RelayEventAck:
    cancel: bool
