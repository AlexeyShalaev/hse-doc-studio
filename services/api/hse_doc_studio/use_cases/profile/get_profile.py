from __future__ import annotations

from hse_doc_studio.core.git_sync.protocols import ILocalAuthorProfile
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.use_cases.profile.profile_view import ProfileView, make_profile_view


class GetProfileUC:
    """Профиль автора этой машины и подпись, которой сейчас ставятся коммиты."""

    def __init__(self, source: ILocalAuthorProfile, fallback: VcsAuthor) -> None:
        self._source = source
        self._fallback = fallback

    async def execute(self) -> ProfileView:
        return make_profile_view(self._source.get(), self._fallback)
