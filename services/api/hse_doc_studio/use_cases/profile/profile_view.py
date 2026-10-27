from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.git_sync.entities import AuthorProfile
from hse_doc_studio.core.vcs.entities import VcsAuthor


@dataclass(frozen=True)
class ProfileView:
    """Профиль и то, чьей подписью на самом деле ставятся коммиты."""

    profile: AuthorProfile | None
    effective: VcsAuthor

    @property
    def is_default(self) -> bool:
        return self.profile is None

    @property
    def commit_preview(self) -> str:
        return f"{self.effective.name} <{self.effective.email}>"


def make_profile_view(profile: AuthorProfile | None, fallback: VcsAuthor) -> ProfileView:
    effective = fallback if profile is None else VcsAuthor(profile.name, profile.email)
    return ProfileView(profile=profile, effective=effective)
