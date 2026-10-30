"""Ретрансляция ИИ через личный раннер: вид задачи `ai.relay`, белый список путей и коды ошибок.

Сервер не открывает адресов в сети пользователя. Раннер сам объявляет в своей конфигурации, какие
OpenAI-совместимые адреса он открывает (имя и базовый URL), сервер знает только имена и вид. Задача несёт
имя адреса и путь из белого списка; тело запроса к модели в очередь не пишется (живёт в памяти api до
конца задачи), ответ модели раннер стримит порциями событий.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.jobs.base import JobPayload, JobResultData

# У `jobs.project_id` нет внешнего ключа: ретрансляция без проекта (список моделей, проверка) пишет нулевой id.
NO_PROJECT_ID = UUID(int=0)
RELAY_TAG = "ai"
ENDPOINT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_AI_ENDPOINTS = 16
# Пределы одной порции событий: столько событий, столько байт данных в одном событии и во всей порции.
MAX_RELAY_EVENTS = 64
MAX_RELAY_EVENT_BYTES = 64 * 1024
MAX_RELAY_BATCH_BYTES = 256 * 1024
# Как часто раннер шлёт пульс, пока порций нет: отмена доходит до него не позже этого срока.
RELAY_KEEPALIVE_S = 2
MAX_RELAY_CONTENT_TYPE = 128


class AiEndpointFlavor(StrEnum):
    """Вид адреса: `ollama` включает поправки OpenAI-пути под Ollama (без tool_choice и stream_options)."""

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


# Расширять только правкой спецификации: раннер отвергает всё, чего здесь нет.
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
    # Раннер: адреса нет в его конфигурации, путь вне белого списка, модель недоступна или молчит, ответ велик.
    endpoint_unknown = "endpoint_unknown"
    path_forbidden = "path_forbidden"
    upstream_unreachable = "upstream_unreachable"
    upstream_timeout = "upstream_timeout"
    response_too_large = "response_too_large"
    cancelled = "cancelled"
    # Сервер: раннер не взял задачу, лимит ретрансляций, раннер не годится, адрес пропал, выключено, тело велико.
    relay_unavailable = "relay_unavailable"
    relay_busy = "relay_busy"
    runner_offline = "runner_offline"
    runner_paused = "runner_paused"
    runner_revoked = "runner_revoked"
    endpoint_missing = "endpoint_missing"
    disabled = "disabled"
    relay_too_large = "relay_too_large"


def is_relay_route(method: str, path: str) -> bool:
    """Путь и метод из белого списка; неизвестное значение это просто «нет»."""
    try:
        return (RelayMethod(method), RelayPath(path)) in RELAY_ROUTES
    except ValueError:
        return False


@dataclass(frozen=True)
class AiRelayPayload(JobPayload):
    """Что переслать: тела запроса здесь нет, раннер забирает его отдельно и сверяет sha256 и размер."""

    # Имя ИИ-адреса, объявленного раннером.
    endpoint: str
    path: RelayPath
    # GET только для models, иначе POST.
    method: RelayMethod
    content_type: str | None
    body_sha256: str | None
    body_size: int
    # Клиент ждёт SSE.
    stream: bool
    # Сколько ждать заголовка ответа модели и сколько тишины терпеть между порциями.
    head_timeout_s: float
    idle_timeout_s: float

    def __post_init__(self) -> None:
        if not ENDPOINT_NAME_RE.fullmatch(self.endpoint):
            raise ValueError(f"invalid endpoint name {self.endpoint!r}")
        if (self.method, self.path) not in RELAY_ROUTES:
            raise ValueError(f"relay route {self.method} {self.path} is not allowed")
        if self.body_size < 0:
            raise ValueError("body_size must not be negative")
        if self.method is RelayMethod.get and (self.body_size or self.body_sha256 is not None):
            raise ValueError("GET carries no body")
        if self.head_timeout_s <= 0 or self.idle_timeout_s <= 0:
            raise ValueError("relay timeouts must be positive")


@dataclass(frozen=True)
class AiRelayResult(JobResultData):
    """Сводка для админки очереди; токены считает чат по самому ответу модели."""

    status_code: int | None
    bytes_out: int
    upstream_ms: int
