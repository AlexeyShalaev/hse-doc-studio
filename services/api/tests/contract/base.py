"""Базовый класс контрактного набора порта.

Наследник задаёт `implementations` (имя -> фабрика) и пишет тесты `test__...` как методы,
получая реализацию через `self.port`. Один набор доказывает одинаковое поведение Json,
InMemory и Postgres. Это единственное место, где допустим тестовый класс.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import pytest


class PortContract:
    implementations: ClassVar[dict[str, Callable[..., Any]]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        impls = getattr(cls, "implementations", None)
        if not impls:
            return

        @pytest.fixture(params=list(impls), ids=list(impls))
        def port(self: Any, request: pytest.FixtureRequest, tmp_path: Any) -> Any:
            return impls[request.param](tmp_path)

        cls.port = port  # type: ignore[attr-defined]
