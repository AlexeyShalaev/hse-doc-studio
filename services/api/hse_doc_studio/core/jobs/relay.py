"""Ретрансляция ИИ через личный раннер: вид задачи `ai.relay`, её нагрузка, итог и белый список путей.

Сервер знает только имя ИИ-адреса, объявленного раннером, и путь из белого списка; базовый URL
живёт в локальной конфигурации раннера. Тела запроса к модели в нагрузке нет: оно лежит в памяти
api до конца задачи и забирается раннером отдельным вызовом, поэтому в очередь (БД) промпты не попадают.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.jobs.base import JobPayload, JobResultData

# Задачи ретрансляции без проекта (список моделей, проверка провайдера); у `jobs.project_id` нет внешнего ключа.
NO_PROJECT_ID = UUID(int=0)
RELAY_TAG = "ai"
ENDPOINT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_AI_ENDPOINTS = 16
# Декодированный размер одного события `data` и число событий в порции.
RELAY_MAX_EVENT_BYTES = 64 * 1024
RELAY_MAX_EVENTS_PER_BATCH = 64
RELAY_KEEPALIVE_S = 2


class AiEndpointFlavor(StrEnum):
    openai = "openai"
    ollama = "ollama"


class RelayPath(StrEnum):
    models = "models"
    chat_completions = "chat/completions"
    completions = "completions"
    embeddings = "embeddings"


class RelayMethod(StrEnum):
    get = "GET"
    post = "POST"


# Расширять только правкой спецификации: раннер исполняет ровно эти пары.
RELAY_ROUTES: frozenset[tuple[RelayMethod, RelayPath]] = frozenset(
    {
        (RelayMethod.get, RelayPath.models),
        (RelayMethod.post, RelayPath.chat_completions),
        (RelayMethod.post, RelayPath.completions),
        (RelayMethod.post, RelayPath.embeddings),
    }
)


class RelayEventKind(StrEnum):
    head = "head"
    data = "data"
    end = "end"
    error = "error"


class RelayErrorCode(StrEnum):
    endpoint_unknown = "endpoint_unknown"
    path_forbidden = "path_forbidden"
    upstream_unreachable = "upstream_unreachable"
    upstream_timeout = "upstream_timeout"
    response_too_large = "response_too_large"
    cancelled = "cancelled"
    relay_unavailable = "relay_unavailable"
    relay_busy = "relay_busy"
    runner_offline = "runner_offline"
    runner_paused = "runner_paused"
    runner_revoked = "runner_revoked"
    endpoint_missing = "endpoint_missing"
    disabled = "disabled"
    relay_too_large = "relay_too_large"


@dataclass(frozen=True)
class AiRelayPayload(JobPayload):
    # Имя ИИ-адреса раннера, URL знает только раннер.
    endpoint: str
    path: RelayPath
    method: RelayMethod
    content_type: str | None
    # Хеш и размер тела запроса; у GET тела нет.
    body_sha256: str | None
    body_size: int
    # Клиент ждёт поток SSE.
    stream: bool
    # Сколько ждать заголовка ответа модели и сколько длится допустимая тишина между порциями.
    head_timeout_s: float
    idle_timeout_s: float

    def __post_init__(self) -> None:
        if not ENDPOINT_NAME_RE.match(self.endpoint):
            raise ValueError(f"bad endpoint name {self.endpoint!r}")
        if (self.method, self.path) not in RELAY_ROUTES:
            raise ValueError(f"{self.method.value} {self.path.value} is not relayed")
        if self.body_size < 0 or (self.method is RelayMethod.get and (self.body_size or self.body_sha256)):
            raise ValueError("GET carries no body")
        if self.head_timeout_s <= 0 or self.idle_timeout_s <= 0:
            raise ValueError("relay timeouts must be positive")


@dataclass(frozen=True)
class AiRelayResult(JobResultData):
    status_code: int | None = None
    bytes_out: int = 0
    upstream_ms: int = 0
