from __future__ import annotations

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.use_cases.ai_relay.client import relay_error_of

RELAY_UNAVAILABLE = "relay_unavailable"
RELAY_BUSY = "relay_busy"


def describe_run_error(exc: BaseException) -> str:
    """Человекочитаемая причина падения рана.

    Уезжает в run.error и оттуда — терминальным событием в чат: пользователь
    должен видеть «модель не поддерживает инструменты», а не «BadRequestError».
    Сбой ретрансляции через раннер описывается по-человечески и с именем раннера.
    """
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


def run_error_code(exc: BaseException) -> str | None:
    """Код для интерфейса: `relay_busy` или `relay_unavailable` у сбоя ретрансляции, иначе None."""
    relay = relay_error_of(exc)
    if relay is None:
        return None
    return RELAY_BUSY if relay.code is RelayErrorCode.relay_busy else RELAY_UNAVAILABLE
