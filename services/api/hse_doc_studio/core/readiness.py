"""Готовность серверного режима: реестр проверок по зонам.

Каждая зона (identity, persistence, jobs, services, пользовательские маршруты) регистрирует свою
проверку. Сервер пускают на старт, только когда все зоны зарегистрированы и все проверки зелёные;
пока хоть одной нет, готовность красная и ``ensure_supported_mode`` отказывает.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ReadinessZone(StrEnum):
    identity = "identity"
    persistence = "persistence"
    jobs = "jobs"
    services = "services"
    per_user_routes = "per_user_routes"


@dataclass(frozen=True)
class ServerReadinessCheck:
    """Проверка одной зоны; ``probe`` возвращает None, когда зелёная, иначе причину."""

    zone: ReadinessZone
    name: str
    probe: Callable[[], str | None]


class ServerReadinessRegistry:
    def __init__(self) -> None:
        self._checks: dict[tuple[ReadinessZone, str], ServerReadinessCheck] = {}

    def register(self, check: ServerReadinessCheck) -> None:
        key = (check.zone, check.name)
        if key in self._checks:
            msg = f"проверка готовности {check.zone}/{check.name} уже зарегистрирована"
            raise ValueError(msg)
        self._checks[key] = check

    def unmet(self) -> list[str]:
        """Что мешает пустить сервер: незарегистрированные зоны и красные проверки."""
        problems = [
            f"{zone}: проверка не зарегистрирована"
            for zone in ReadinessZone
            if not any(check.zone is zone for check in self._checks.values())
        ]
        for check in self._checks.values():
            reason = check.probe()
            if reason is not None:
                problems.append(f"{check.zone}/{check.name}: {reason}")
        return problems


server_readiness = ServerReadinessRegistry()
