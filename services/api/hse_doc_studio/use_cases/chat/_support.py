from __future__ import annotations

import re

from hse_doc_studio.core.ai_gateway.errors import (
    AI_MODEL_NOT_ALLOWED,
    AI_PROVIDER_UNAVAILABLE,
    AiModelNotAllowedError,
    AiProviderUnavailableError,
)
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.core.quotas.errors import QUOTA_EXCEEDED, QuotaExceededError
from hse_doc_studio.core.quotas.messages import describe_quota_exceeded
from hse_doc_studio.use_cases.ai_relay.client import AiRelayError, relay_error_of

RELAY_UNAVAILABLE = "relay_unavailable"
RELAY_BUSY = "relay_busy"
MODEL_CONTEXT_EXCEEDED = "model_context_exceeded"


def describe_run_error(exc: BaseException) -> str:
    """Человекочитаемая причина падения рана.

    Уезжает в run.error и оттуда — терминальным событием в чат: пользователь
    должен видеть «модель не поддерживает инструменты», а не «BadRequestError».
    Сбой ретрансляции через раннер описывается по-человечески и с именем раннера.
    """
    gateway = _gateway_message(exc)
    if gateway is not None:
        return gateway
    relay = relay_error_of(exc)
    if relay is not None:
        return _relay_message(relay)
    overflow = _context_overflow(exc)
    if overflow is not None:
        return overflow
    name = type(exc).__name__
    detail = str(exc).strip()
    if not detail:
        return name
    return f"{name}: {detail[:400]}"


def _relay_message(relay: AiRelayError) -> str:
    """Почему модель через раннер не ответила: причина и что сделать, а не общее «раннер не ответил»."""
    name = relay.runner_name or "?"
    code = relay.code
    if code is RelayErrorCode.relay_busy:
        return localized_error(
            "Слишком много запросов к раннеру одновременно, попробуйте через минуту.",
            "Too many requests to the runner at once, try again in a minute.",
        )
    if code is RelayErrorCode.upstream_unreachable:
        return localized_error(
            f"Раннер «{name}» на связи, но модель на его компьютере не отвечает. Запустите Ollama или другой сервер "
            "моделей на этом компьютере.",
            f'Runner "{name}" is online, but the model on its computer does not answer. Start Ollama or the other '
            "model server on that computer.",
        )
    if code is RelayErrorCode.upstream_timeout:
        return localized_error(
            f"Модель за раннером «{name}» не ответила вовремя. Попробуйте модель поменьше или повторите позже.",
            f'The model behind runner "{name}" did not answer in time. Try a smaller model or retry later.',
        )
    if code in {RelayErrorCode.runner_offline, RelayErrorCode.runner_paused, RelayErrorCode.runner_revoked}:
        state = {
            RelayErrorCode.runner_offline: ("не в сети", "is offline"),
            RelayErrorCode.runner_paused: ("на паузе", "is paused"),
            RelayErrorCode.runner_revoked: ("отозван", "was revoked"),
        }[code]
        return localized_error(
            f"Раннер «{name}» {state[0]}. Запустите локальную Студию на этом компьютере или выберите другую модель.",
            f'Runner "{name}" {state[1]}. Start the local Studio on that computer or pick another model.',
        )
    if code is RelayErrorCode.endpoint_missing:
        return localized_error(
            f"Раннер «{name}» больше не открывает эту модель. Откройте её для облака в локальной Студии.",
            f'Runner "{name}" no longer opens this model. Open it for the cloud in the local Studio.',
        )
    return localized_error(
        f"Раннер «{name}» не ответил. Запустите его или выберите другую модель.",
        f'Runner "{name}" did not respond. Start it or pick another model.',
    )


_CONTEXT_RE = re.compile(r"request \((\d+) tokens\) exceeds the available context size \((\d+) tokens\)")


def _context_overflow(exc: BaseException) -> str | None:
    """Ollama отказывает 400, когда запрос не помещается в окно модели (по умолчанию 4096 токенов)."""
    found = _CONTEXT_RE.search(str(exc))
    if found is None:
        return None
    need, have = found.group(1), found.group(2)
    return localized_error(
        f"Запрос ({need} токенов) не помещается в окно модели ({have}). В Ollama увеличьте контекст "
        "(num_ctx, например 16384) или выберите модель с большим окном.",
        f"The request ({need} tokens) does not fit the model window ({have}). Raise the context in Ollama "
        "(num_ctx, for example 16384) or pick a model with a larger window.",
    )


def _gateway_message(exc: BaseException) -> str | None:
    """Отказы ИИ-шлюза сервера: квота токенов, модель вне списка, провайдер временно закрыт."""
    if isinstance(exc, QuotaExceededError):
        return describe_quota_exceeded(exc)
    if isinstance(exc, AiModelNotAllowedError):
        return localized_error(
            f"Модель «{exc.model}» не разрешена на этом провайдере. Выберите другую.",
            f'Model "{exc.model}" is not allowed on this provider. Pick another one.',
        )
    if isinstance(exc, AiProviderUnavailableError):
        return localized_error(
            f"Провайдер «{exc.provider_name}» временно недоступен. Попробуйте позже или выберите другой.",
            f'Provider "{exc.provider_name}" is temporarily unavailable. Try later or pick another one.',
        )
    return None


def run_error_code(exc: BaseException) -> str | None:
    """Код для интерфейса: `quota_exceeded`, `ai_model_not_allowed`, `ai_provider_unavailable`, `relay_busy`,
    `relay_unavailable`, `model_context_exceeded` или None."""
    if isinstance(exc, QuotaExceededError):
        return QUOTA_EXCEEDED
    if isinstance(exc, AiModelNotAllowedError):
        return AI_MODEL_NOT_ALLOWED
    if isinstance(exc, AiProviderUnavailableError):
        return AI_PROVIDER_UNAVAILABLE
    relay = relay_error_of(exc)
    if relay is None:
        return MODEL_CONTEXT_EXCEEDED if _context_overflow(exc) is not None else None
    return RELAY_BUSY if relay.code is RelayErrorCode.relay_busy else RELAY_UNAVAILABLE
