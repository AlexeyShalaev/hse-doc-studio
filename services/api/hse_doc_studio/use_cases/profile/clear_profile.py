from __future__ import annotations

import structlog

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.vcs.author import PROFILE_EMAIL_KEY, PROFILE_NAME_KEY
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.use_cases.profile.profile_view import ProfileView, make_profile_view

logger = structlog.get_logger()


class ClearProfileUC:
    """Забыть профиль: новые коммиты снова подписываются служебной подписью, старые не меняются."""

    def __init__(self, settings_repo: ISettingsRepository, fallback: VcsAuthor) -> None:
        self._settings_repo = settings_repo
        self._fallback = fallback

    async def execute(self) -> ProfileView:
        stored = await self._settings_repo.get()
        if PROFILE_NAME_KEY in stored or PROFILE_EMAIL_KEY in stored:
            await self._settings_repo.save({**stored, PROFILE_NAME_KEY: None, PROFILE_EMAIL_KEY: None})
            logger.info("author profile cleared")
        return make_profile_view(None, self._fallback)
