"""Фикстура `stand` серверных тестов маршрута подписания; без extra server её нет (модули не собираются)."""

from __future__ import annotations

import importlib.util

from tests.integration.api.signing_routes.preset_stand import preset_packs

__all__: list[str] = ["preset_packs"]

if importlib.util.find_spec("sqlalchemy") is not None:
    from tests.integration.api.personal.conftest import stand

    __all__ += ["stand"]
