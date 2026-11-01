"""Контрактный набор ISettingsRepository: Json и InMemory ведут себя одинаково."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from hse_doc_studio.infra.persistence.settings import JsonSettingsRepository

from tests.contract.base import PortContract
from tests.fakes.settings import InMemorySettingsRepository

_FACTORIES: dict[str, Callable[[Path], Any]] = {
    "inmemory": lambda _root: InMemorySettingsRepository(),
    "json": lambda root: JsonSettingsRepository(root / "data"),
}


class TestSettingsContract(PortContract):
    implementations = _FACTORIES

    async def test__get__nothing_saved__returns_empty_dict(self, port: Any) -> None:
        assert await port.get() == {}

    async def test__get__after_save__returns_saved_values(self, port: Any) -> None:
        await port.save({"theme": "dark", "latex_passes": 4})
        assert await port.get() == {"theme": "dark", "latex_passes": 4}

    async def test__save__replaces_previous_document(self, port: Any) -> None:
        await port.save({"theme": "dark", "latex_passes": 4})
        await port.save({"theme": "light"})
        assert await port.get() == {"theme": "light"}

    async def test__get__returned_dict_is_a_copy(self, port: Any) -> None:
        await port.save({"theme": "dark"})
        (await port.get())["theme"] = "light"
        assert (await port.get())["theme"] == "dark"

    async def test__save__keeps_non_ascii_values(self, port: Any) -> None:
        await port.save({"default_agent_persona_instructions": "Пиши коротко"})
        assert (await port.get())["default_agent_persona_instructions"] == "Пиши коротко"
