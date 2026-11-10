"""HTTP-вид отказа штамповки: метка подписи не легла на PDF (400, тело `{detail, code}`).

Роутеры подписей и пакета сдачи ловят `ValueError` сами и отвечают 400 с тем же текстом. Этот обработчик
нужен там, где ошибку штамповки никто не ловит: действия маршрута подписания, после которых маршрут
фиксирует документ (согласие, своя картинка, плашка). Без него такой отказ стал бы безликим 500.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.signatures.errors import StampingError


async def _stamping_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StampingError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=400, content={"detail": str(exc), "code": exc.code})


def install_stamping_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StampingError, _stamping_handler)
