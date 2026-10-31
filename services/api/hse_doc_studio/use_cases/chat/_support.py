from __future__ import annotations

from hse_doc_studio.core.ai_gateway.errors import (
    AI_MODEL_NOT_ALLOWED,
    AI_PROVIDER_UNAVAILABLE,
    AiModelNotAllowedError,
    AiProviderUnavailableError,
)
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.core.quotas.errors import QUOTA_EXCEEDED, QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.use_cases.ai_relay.client import relay_error_of

RELAY_UNAVAILABLE = "relay_unavailable"
RELAY_BUSY = "relay_busy"


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
        if relay.code is RelayErrorCode.relay_busy:
            return localized_error(
                "Слишком много запросов к раннеру одновременно, попробуйте через минуту.",
                "Too many requests to the runner at once, try again in a minute.",
            )
        name = relay.runner_name or "?"
        return localized_error(
            f"Раннер «{name}» не ответил. Запустите его или выберите другую модель.",
            f'Runner "{name}" did not respond. Start it or pick another model.',
        )
    name = type(exc).__name__
    detail = str(exc).strip()
    if not detail:
        return name
    return f"{name}: {detail[:400]}"


def _gateway_message(exc: BaseException) -> str | None:
    """Отказы ИИ-шлюза сервера: квота токенов, модель вне списка, провайдер временно закрыт."""
    if isinstance(exc, QuotaExceededError):
        period = "сутки" if exc.kind is QuotaKind.ai_tokens_day else "месяц"
        period_en = "day" if exc.kind is QuotaKind.ai_tokens_day else "month"
        until = f" Сбросится {exc.resets_at:%d.%m.%Y %H:%M} UTC." if exc.resets_at is not None else ""
        until_en = f" Resets {exc.resets_at:%Y-%m-%d %H:%M} UTC." if exc.resets_at is not None else ""
        return localized_error(
            f"Исчерпан лимит токенов ИИ за {period}: {exc.used} из {exc.limit}.{until}",
            f"AI token limit for the {period_en} is used up: {exc.used} of {exc.limit}.{until_en}",
        )
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
    `relay_unavailable` или None."""
    if isinstance(exc, QuotaExceededError):
        return QUOTA_EXCEEDED
    if isinstance(exc, AiModelNotAllowedError):
        return AI_MODEL_NOT_ALLOWED
    if isinstance(exc, AiProviderUnavailableError):
        return AI_PROVIDER_UNAVAILABLE
    relay = relay_error_of(exc)
    if relay is None:
        return None
    return RELAY_BUSY if relay.code is RelayErrorCode.relay_busy else RELAY_UNAVAILABLE
