from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any, cast

import pytest
from hse_doc_studio.infra.db.session import SessionProvider, live_ambient
from hse_doc_studio.infra.db.uow import SqlUnitOfWork

pytestmark = pytest.mark.unit


class _Tx:
    def __init__(self, session: _Session) -> None:
        self._session = session

    async def __aenter__(self) -> _Tx:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        self._session.outcome = "rollback" if exc_type else "commit"


class _Session:
    def __init__(self) -> None:
        self.outcome: str | None = None

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None

    def begin(self) -> _Tx:
        return _Tx(self)


class _Maker:
    def __init__(self) -> None:
        self.sessions: list[_Session] = []

    def __call__(self) -> _Session:
        self.sessions.append(_Session())
        return self.sessions[-1]

    def begin(self) -> _Session:
        # как async_sessionmaker.begin(): сессия, у которой вход открывает транзакцию
        session = self()
        return session


def _provider() -> tuple[SessionProvider, _Maker]:
    maker = _Maker()
    return SessionProvider(cast("Any", maker)), maker


async def test__begin__commits_on_exit_and_clears_ambient() -> None:
    provider, maker = _provider()

    async with provider.begin():
        assert live_ambient() is not None

    assert live_ambient() is None
    assert maker.sessions[0].outcome == "commit"


async def test__begin__exception__rolls_back() -> None:
    provider, maker = _provider()

    with pytest.raises(ValueError, match="boom"):
        async with provider.begin():
            raise ValueError("boom")

    assert maker.sessions[0].outcome == "rollback"
    assert live_ambient() is None


async def test__begin__nested__joins_outer_transaction() -> None:
    provider, maker = _provider()

    async with provider.begin():
        outer = live_ambient()
        async with provider.begin():
            assert live_ambient() is outer
        assert live_ambient() is outer
        assert outer is not None
        assert not outer.closed

    assert len(maker.sessions) == 1


async def test__use__inside_begin__returns_ambient_session() -> None:
    provider, maker = _provider()

    async with provider.begin(), provider.use() as session:
        assert session is maker.sessions[0]

    assert len(maker.sessions) == 1


async def test__use__without_begin__opens_own_session_per_call() -> None:
    provider, maker = _provider()

    async with provider.use() as first:
        pass
    async with provider.use() as second:
        pass

    assert first is not second
    assert len(maker.sessions) == 2


async def test__closed_transaction__inherited_by_background_task__is_not_reused() -> None:
    provider, maker = _provider()
    seen: list[object] = []

    async def background() -> None:
        await gate.wait()
        seen.append(live_ambient())
        async with provider.use() as session:
            seen.append(session)

    gate = asyncio.Event()
    async with provider.begin():
        task = asyncio.create_task(background())  # копия контекста несёт ambient
    gate.set()
    await task

    assert seen[0] is None
    assert seen[1] is maker.sessions[1]
    assert maker.sessions[0].outcome == "commit"


async def test__unit_of_work__begin__delegates_to_provider() -> None:
    provider, maker = _provider()

    async with SqlUnitOfWork(provider).begin():
        assert live_ambient() is not None

    assert maker.sessions[0].outcome == "commit"
