"""Конвертация office в PDF через постоянный Gotenberg: раннеру без docker.sock контейнер не поднять."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger()

_CONVERT_ROUTE = "/forms/libreoffice/convert"


class GotenbergConverter:
    """`IOfficeConvertService` поверх готового адреса; образ из задачи не используется."""

    def __init__(self, base_url: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = base_url.rstrip("/") + _CONVERT_ROUTE
        self._timeout_s = timeout_s
        self._transport = transport

    async def convert_to_pdf(self, source: Path, image: str | None = None) -> bytes | None:
        """PDF или None: предпросмотр не должен ронять задачу, как у встроенного конвертера."""
        try:
            data = await asyncio.to_thread(source.read_bytes)
            async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
                response = await client.post(self._url, files={"files": (source.name, data)})
        except (OSError, httpx.HTTPError) as exc:
            logger.warning("runner office: conversion failed", source=source.name, exc=type(exc).__name__)
            return None
        if response.status_code != 200:
            logger.warning("runner office: gotenberg error", status=response.status_code)
            return None
        return response.content
