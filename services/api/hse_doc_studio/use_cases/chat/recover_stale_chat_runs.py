from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from hse_doc_studio.core.enums import AgentRunStatus, Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChatRepository,
    ISettingsRepository,
)

logger = structlog.get_logger()

_STALE = (AgentRunStatus.pending, AgentRunStatus.running)
_INTERFACE_LANGUAGE_KEY = "interface_language"
_SERVER_RESTARTED = {
    Lang.ru: "сервер перезапущен во время выполнения хода",
    Lang.en: "the server was restarted while the turn was running",
}


@dataclass
class RecoverStaleChatRunsOutput:
    recovered_runs: int


class RecoverStaleChatRunsUC:
    """Startup hook: mark runs left pending/running by a previous process as
    interrupted, so the per-session in-memory busy guard (empty after restart)
    and the UI agree (mirrors RecoverStaleCompilesUC)."""

    def __init__(
        self,
        locator: IProjectLocator,
        chat_repo: IChatRepository,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._locator = locator
        self._chat_repo = chat_repo
        self._settings_repo = settings_repo

    async def execute(self) -> RecoverStaleChatRunsOutput:
        now = datetime.now(timezone.utc)
        # Runs at startup (no request context), so resolve the saved interface
        # language directly as the fallback.
        lang = current_interface_language((await self._settings_repo.get()).get(_INTERFACE_LANGUAGE_KEY))
        error_text = _SERVER_RESTARTED.get(lang, _SERVER_RESTARTED[Lang.ru])
        recovered = 0
        for folder in await self._locator.list_all():
            for run_id in self._chat_repo.list_all_run_ids(folder):
                run = self._chat_repo.get_run(folder, run_id)
                if run is None or run.status not in _STALE:
                    continue
                run.status = AgentRunStatus.interrupted
                run.finished_at = now
                run.error = error_text
                self._chat_repo.save_run(run)
                recovered += 1
        if recovered:
            logger.info("recovered stale agent runs", count=recovered)
        return RecoverStaleChatRunsOutput(recovered_runs=recovered)
