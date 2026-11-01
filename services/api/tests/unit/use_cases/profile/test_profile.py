from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import ProfileInvalidError
from hse_doc_studio.infra.vcs.profile_source import ConfigAuthorProfile
from hse_doc_studio.use_cases.profile.clear_profile import ClearProfileUC
from hse_doc_studio.use_cases.profile.get_profile import GetProfileUC
from hse_doc_studio.use_cases.profile.update_profile import UpdateProfileInput, UpdateProfileUC

pytestmark = pytest.mark.unit

_BOT = VcsAuthor("HSE Studio", "bot@hse-studio.local")


class _Repo:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = dict(data or {})
        self.saves = 0

    def read_local(self) -> dict[str, Any]:
        return dict(self.data)

    async def get(self) -> dict[str, Any]:
        return dict(self.data)

    async def save(self, settings: dict[str, Any]) -> None:
        self.data = dict(settings)
        self.saves += 1


async def test__get__no_profile__is_default_with_bot_preview() -> None:
    view = await GetProfileUC(ConfigAuthorProfile(_Repo()), _BOT).execute()

    assert view.profile is None
    assert view.is_default is True
    assert view.effective == _BOT
    assert view.commit_preview == "HSE Studio <bot@hse-studio.local>"


async def test__update__valid__persists_normalized_and_keeps_other_settings() -> None:
    repo = _Repo({"theme": "dark"})

    view = await UpdateProfileUC(repo, _BOT).execute(UpdateProfileInput("  Алиса  Иванова ", "Alice@Example.ORG"))

    assert repo.data == {"theme": "dark", "profile_name": "Алиса Иванова", "profile_email": "Alice@example.org"}
    assert view.is_default is False
    assert view.commit_preview == "Алиса Иванова <Alice@example.org>"
    assert (await GetProfileUC(ConfigAuthorProfile(repo), _BOT).execute()).profile == view.profile


async def test__update__both_fields_invalid__reports_both_and_writes_nothing() -> None:
    repo = _Repo()

    with pytest.raises(ProfileInvalidError) as exc:
        await UpdateProfileUC(repo, _BOT).execute(UpdateProfileInput("<x>", "nope"))

    assert [e.code for e in exc.value.errors] == ["name_invalid", "email_invalid"]
    assert repo.saves == 0


async def test__update__one_field_invalid__reports_only_that_field() -> None:
    with pytest.raises(ProfileInvalidError) as exc:
        await UpdateProfileUC(_Repo(), _BOT).execute(UpdateProfileInput("Алиса", "alice@localhost"))

    assert [e.code for e in exc.value.errors] == ["email_invalid"]


async def test__clear__forgets_profile_and_returns_default() -> None:
    repo = _Repo({"profile_name": "Алиса", "profile_email": "alice@example.org", "theme": "dark"})

    view = await ClearProfileUC(repo, _BOT).execute()

    assert view.is_default is True
    assert repo.data == {"profile_name": None, "profile_email": None, "theme": "dark"}


async def test__clear__nothing_stored__does_not_write() -> None:
    repo = _Repo({"theme": "dark"})

    await ClearProfileUC(repo, _BOT).execute()

    assert repo.saves == 0
