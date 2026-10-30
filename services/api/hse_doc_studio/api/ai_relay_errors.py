"""HTTP-вид отказов ретрансляции ИИ: 503 `relay_unavailable`, 429 `relay_busy`, 422 `ai_provider_runner_invalid`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.use_cases.ai_providers.relay_info import AiProviderRunnerInvalidError
from hse_doc_studio.use_cases.ai_relay.client import AiRelayError

RELAY_UNAVAILABLE = "relay_unavailable"
RELAY_BUSY = "relay_busy"


def relay_error_body(exc: AiRelayError) -> tuple[int, dict[str, str]]:
    """Статус и тело `{detail, code}`; текст называет раннер, если он известен."""
    if exc.code is RelayErrorCode.relay_busy:
        detail = localized_error(
            "Слишком много запросов к раннеру одновременно, попробуйте через минуту.",
            "Too many requests to the runner at once, try again in a minute.",
        )
        return 429, {"detail": detail, "code": RELAY_BUSY}
    name = exc.runner_name
    detail = localized_error(
        f"Раннер «{name}» не ответил. Запустите его или выберите другую модель."
        if name
        else "Раннер не ответил. Запустите его или выберите другую модель.",
        f'Runner "{name}" did not respond. Start it or pick another model.'
        if name
        else "The runner did not respond. Start it or pick another model.",
    )
    return 503, {"detail": detail, "code": RELAY_UNAVAILABLE}


async def _relay_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AiRelayError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    status, body = relay_error_body(exc)
    return JSONResponse(status_code=status, content=body)


async def _runner_invalid_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AiProviderRunnerInvalidError)  # noqa: S101
    return JSONResponse(status_code=422, content={"detail": str(exc), "code": exc.code})


def install_ai_relay_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AiRelayError, _relay_handler)
    app.add_exception_handler(AiProviderRunnerInvalidError, _runner_invalid_handler)
