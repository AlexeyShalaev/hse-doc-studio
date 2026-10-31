"""Какие ошибки SDK провайдеров временные (повтор и замена имеют смысл), а какие нет (ключ, запрос, модель)."""

from __future__ import annotations

import asyncio

import anthropic
import httpx2
import openai

_TRANSIENT_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})


def is_transient_ai_error(exc: BaseException) -> bool:
    if isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return True  # включая таймауты соединения
    if isinstance(exc, (openai.APIStatusError, anthropic.APIStatusError)):
        return exc.status_code in _TRANSIENT_STATUS
    return isinstance(exc, (asyncio.TimeoutError, httpx2.TransportError, ConnectionError))
