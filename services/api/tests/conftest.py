from __future__ import annotations

import pytest

pytest_plugins = [
    "tests.fixtures.app",
    "tests.fixtures.paths",
]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = item.path.parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)
