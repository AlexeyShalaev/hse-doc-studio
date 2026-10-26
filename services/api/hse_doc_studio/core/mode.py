"""Режим работы инстанса: локальная установка или общий сервер."""

from __future__ import annotations

from enum import StrEnum


class StudioMode(StrEnum):
    local = "local"
    server = "server"
