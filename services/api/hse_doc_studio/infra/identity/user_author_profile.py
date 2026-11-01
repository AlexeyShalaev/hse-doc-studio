from __future__ import annotations

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.git_sync.entities import AuthorProfile
from hse_doc_studio.core.vcs.author import normalize_email, normalize_name
from hse_doc_studio.core.vcs.errors import ProfileValidationError


class UserAuthorProfile:
    """Профиль автора на сервере: подпись коммитов вошедшего человека.

    Резолвер уже положил её в актора (свои имя и адрес, e-mail аккаунта по согласию, иначе noreply),
    поэтому у человека профиль есть всегда и `profile_required` в git-синхронизации выполнен сам.
    Без человека (фон, анонимный запрос) профиля нет.
    """

    def get(self) -> AuthorProfile | None:
        actor = current_actor()
        if actor is None or actor.kind is ActorKind.local:
            return None
        try:
            return AuthorProfile(normalize_name(actor.name), normalize_email(actor.email, require_domain_dot=False))
        except ProfileValidationError:
            return None
