from __future__ import annotations

from hse_doc_studio.core.git_sync.entities import AuthorProfile
from hse_doc_studio.core.repositories import ILocalSettingsReader
from hse_doc_studio.core.vcs.author import PROFILE_EMAIL_KEY, PROFILE_NAME_KEY, normalize_email, normalize_name
from hse_doc_studio.core.vcs.errors import ProfileValidationError


class ConfigAuthorProfile:
    """Профиль автора из config.json, читается на каждый коммит.

    Никогда не бросает: файл настроек недоступен или в нём негодные значения означают
    «профиля нет», и коммит подписывается служебной подписью.
    """

    def __init__(self, settings: ILocalSettingsReader) -> None:
        self._settings = settings

    def get(self) -> AuthorProfile | None:
        try:
            stored = self._settings.read_local()
            name = stored.get(PROFILE_NAME_KEY)
            email = stored.get(PROFILE_EMAIL_KEY)
            if not isinstance(name, str) or not isinstance(email, str):
                return None
            return AuthorProfile(normalize_name(name), normalize_email(email))
        except (ProfileValidationError, OSError, ValueError, AttributeError):
            return None
