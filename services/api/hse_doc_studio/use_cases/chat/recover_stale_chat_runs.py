from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from hse_doc_studio.core.enums import AgentRunStatus, Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import (
    IChatRepository,
    IProjectIndexRepository,
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
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._project_index_repo = project_index_repo
        self._chat_repo = chat_repo
        self._settings_repo = settings_repo

    async def execute(self) -> RecoverStaleChatRunsOutput:
        now = datetime.now(timezone.utc)
        # Runs at startup (no request context), so resolve the saved interface
        # language directly as the fallback.
        lang = current_interface_language(self._settings_repo.get().get(_INTERFACE_LANGUAGE_KEY))
        error_text = _SERVER_RESTARTED.get(lang, _SERVER_RESTARTED[Lang.ru])
        recovered = 0
        for folder in self._project_index_repo.list_known():
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
