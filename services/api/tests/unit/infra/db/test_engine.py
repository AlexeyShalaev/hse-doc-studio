from __future__ import annotations

import pytest
from hse_doc_studio.infra.db.engine import async_dsn
from hse_doc_studio.infra.db.errors import DbConfigError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("prefix", ["postgresql", "postgres", "postgresql+asyncpg"])
def test__async_dsn__adds_asyncpg_driver(prefix: str) -> None:
    assert async_dsn(f"{prefix}://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


@pytest.mark.parametrize("dsn", [None, "", "  ", "mysql://u@h/db", "postgresql+psycopg://u@h/db", "not a url"])
def test__async_dsn__invalid__raises(dsn: str | None) -> None:
    with pytest.raises(DbConfigError):
        async_dsn(dsn)
