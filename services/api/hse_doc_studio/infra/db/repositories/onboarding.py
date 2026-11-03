"""Онбординг в Postgres: строка `user_onboarding` текущего пользователя."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import ActorRequired, require_actor
from hse_doc_studio.core.onboarding.entities import OnboardingState, OnboardingStatus
from hse_doc_studio.infra.db.orm.onboarding import UserOnboardingRow
from hse_doc_studio.infra.db.session import SessionProvider


def _user_id() -> str:
    actor = require_actor()
    if actor.id is None or actor.is_guest:
        raise ActorRequired("онбординг есть только у вошедшего пользователя")
    return actor.id


class SqlOnboardingRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    @staticmethod
    def _to_entity(row: UserOnboardingRow) -> OnboardingState:
        return OnboardingState(
            status=OnboardingStatus(row.status),
            scenario_version=row.scenario_version,
            step=row.step,
            answers={str(k): str(v) for k, v in (row.answers or {}).items()},
            started_at=row.started_at,
            finished_at=row.finished_at,
            updated_at=row.updated_at,
        )

    async def get(self) -> OnboardingState | None:
        user_id = _user_id()
        async with self._sessions.use() as session:
            row = await session.get(UserOnboardingRow, user_id)
            return self._to_entity(row) if row else None

    async def save(self, state: OnboardingState) -> None:
        user_id = _user_id()
        values = {
            "status": state.status.value,
            "scenario_version": state.scenario_version,
            "step": state.step,
            "answers": dict(state.answers),
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "updated_at": state.updated_at or datetime.now(UTC),
        }
        async with self._sessions.use() as session:
            stmt = pg_insert(UserOnboardingRow).values(user_id=user_id, **values)
            await session.execute(stmt.on_conflict_do_update(index_elements=[UserOnboardingRow.user_id], set_=values))


class MigratedExistingUserProbe:
    """Сервер: давних пользователей отметила миграция (`suggested`), без строки человек новый."""

    async def is_existing_user(self) -> bool:
        return False
