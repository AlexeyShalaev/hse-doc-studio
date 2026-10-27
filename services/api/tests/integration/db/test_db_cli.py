from __future__ import annotations

import pytest
from hse_doc_studio import cli
from hse_doc_studio.api.config import settings
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg


async def _run(argv: list[str]) -> int:
    # main() сам запускает цикл событий, из работающего цикла его вызывает поток
    import asyncio

    return await asyncio.to_thread(cli.main, argv)


async def test__db_cli__upgrade_current_check__flow(
    pg_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings.db, "dsn", pg_engine.url.render_as_string(hide_password=False))

    assert await _run(["db", "check"]) == 1
    assert await _run(["db", "upgrade"]) == 0
    assert await _run(["db", "current"]) == 0
    assert await _run(["db", "check"]) == 0
    assert "head: 0001" in capsys.readouterr().out


def test__db_cli__without_dsn__exits_with_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.db, "dsn", None)

    assert cli.main(["db", "current"]) == 2
