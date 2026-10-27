from __future__ import annotations

import importlib.util
import os

import pytest

from tests.fixtures.pg import PG_DSN_ENV

pytest_plugins = [
    "tests.fixtures.actors",
    "tests.fixtures.app",
    "tests.fixtures.git_remote",
    "tests.fixtures.paths",
    "tests.fixtures.pg",
    "tests.fixtures.s3",
    "tests.fixtures.server_app",
]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = item.path.parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)
        # skip внутри session-фикстуры ломает последующие async-фикстуры, поэтому pg пропускаем до setup
        if item.get_closest_marker("pg") and not os.environ.get(PG_DSN_ENV):
            item.add_marker(pytest.mark.skip(reason=f"{PG_DSN_ENV} не задан"))


# Без extra server (CI-задача test-no-server) серверные тесты не собираются: они импортируют sqlalchemy и boto3.
collect_ignore_glob: list[str] = []
if importlib.util.find_spec("sqlalchemy") is None:
    collect_ignore_glob += ["integration/db/*", "unit/infra/db/*"]
if importlib.util.find_spec("argon2") is None:
    collect_ignore_glob += ["unit/infra/identity/*"]
if importlib.util.find_spec("boto3") is None or importlib.util.find_spec("moto") is None:
    collect_ignore_glob += ["integration/test_s3_fixtures.py"]
