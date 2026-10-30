"""Раннеры в админке: страницы раннеров и токенов регистрации, сводка для KPI и пикер для фильтра очереди."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.admin import IRunnerAdminReader, RegistrationTokenQuery, RunnerQuery, RunnerSummary
from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner
from hse_doc_studio.core.listing import PICKER_LIMIT, Paged, PickerResult, Window, clamp_limit
from hse_doc_studio.use_cases.admin.users import require_admin


@dataclass(frozen=True)
class RunnerPage:
    page: Paged[Runner]
    # Момент, от которого считались статусы: тем же моментом их считает и ответ.
    as_of: datetime


def _clamped(window: Window) -> Window:
    return Window(limit=clamp_limit(window.limit), offset=max(0, window.offset))


class ListRunnersUC:
    def __init__(self, reader: IRunnerAdminReader, *, clock: Clock = utc_now) -> None:
        self._reader = reader
        self._clock = clock

    async def execute(self, actor: Actor, query: RunnerQuery) -> RunnerPage:
        require_admin(actor)
        now = self._clock()
        page = await self._reader.list_runners(replace(query, window=_clamped(query.window)), now)
        return RunnerPage(page=page, as_of=now)


class RunnerSummaryUC:
    def __init__(self, reader: IRunnerAdminReader, *, clock: Clock = utc_now) -> None:
        self._reader = reader
        self._clock = clock

    async def execute(self, actor: Actor) -> RunnerSummary:
        require_admin(actor)
        return await self._reader.summary(self._clock())


class ListRegistrationTokensUC:
    def __init__(self, reader: IRunnerAdminReader, *, clock: Clock = utc_now) -> None:
        self._reader = reader
        self._clock = clock

    async def execute(self, actor: Actor, query: RegistrationTokenQuery) -> Paged[RegistrationToken]:
        require_admin(actor)
        return await self._reader.list_tokens(replace(query, window=_clamped(query.window)), self._clock())


class PickRunnersUC:
    def __init__(self, reader: IRunnerAdminReader) -> None:
        self._reader = reader

    async def execute(self, actor: Actor, q: str | None, limit: int = PICKER_LIMIT) -> PickerResult:
        require_admin(actor)
        return await self._reader.pick(q, clamp_limit(limit, PICKER_LIMIT))
