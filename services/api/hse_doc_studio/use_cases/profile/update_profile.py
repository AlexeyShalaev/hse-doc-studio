from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.git_sync.entities import AuthorProfile
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.vcs.author import PROFILE_EMAIL_KEY, PROFILE_NAME_KEY, normalize_email, normalize_name
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import ProfileInvalidError, ProfileValidationError
from hse_doc_studio.use_cases.profile.profile_view import ProfileView, make_profile_view

logger = structlog.get_logger()


@dataclass
class UpdateProfileInput:
    name: str
    email: str


class UpdateProfileUC:
    """Сохранить имя и e-mail, которыми подписываются коммиты на этой машине.

    Проверяются оба поля, и `ProfileInvalidError` перечисляет все негодные.
    """

    def __init__(self, settings_repo: ISettingsRepository, fallback: VcsAuthor) -> None:
        self._settings_repo = settings_repo
        self._fallback = fallback

    async def execute(self, inp: UpdateProfileInput) -> ProfileView:
        errors: list[ProfileValidationError] = []
        name = email = ""
        try:
            name = normalize_name(inp.name)
        except ProfileValidationError as exc:
            errors.append(exc)
        try:
            email = normalize_email(inp.email)
        except ProfileValidationError as exc:
            errors.append(exc)
        if errors:
            raise ProfileInvalidError(errors)
        stored = await self._settings_repo.get()
        await self._settings_repo.save({**stored, PROFILE_NAME_KEY: name, PROFILE_EMAIL_KEY: email})
        logger.info("author profile saved")
        return make_profile_view(AuthorProfile(name, email), self._fallback)
