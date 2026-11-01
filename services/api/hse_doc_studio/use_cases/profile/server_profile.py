"""Профиль автора на сервере: те же ручки `/profile`, но подпись хранится в аккаунте человека.

Своё имя и адрес для коммитов это `commit_name` и `commit_email` пользователя; «забыть профиль»
возвращает подпись по умолчанию (имя аккаунта и noreply-адрес).
"""

from __future__ import annotations

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.git_sync.entities import AuthorProfile
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.use_cases.identity.account_profile import AccountView, UpdateAccountInput, UpdateAccountUC
from hse_doc_studio.use_cases.profile.clear_profile import ClearProfileUC
from hse_doc_studio.use_cases.profile.profile_view import ProfileView, make_profile_view
from hse_doc_studio.use_cases.profile.update_profile import UpdateProfileInput, UpdateProfileUC


def _user_id() -> str:
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor.id


def _view(account: AccountView) -> ProfileView:
    identity = account.identity
    return make_profile_view(AuthorProfile(identity.name, identity.email), VcsAuthor(identity.name, identity.email))


class ServerUpdateProfileUC(UpdateProfileUC):
    def __init__(self, accounts: UpdateAccountUC) -> None:
        self._accounts = accounts

    async def execute(self, inp: UpdateProfileInput) -> ProfileView:
        return _view(
            await self._accounts.execute(
                _user_id(),
                UpdateAccountInput(commit_name=inp.name, commit_email=inp.email, commit_use_account_email=False),
            )
        )


class ServerClearProfileUC(ClearProfileUC):
    def __init__(self, accounts: UpdateAccountUC) -> None:
        self._accounts = accounts

    async def execute(self) -> ProfileView:
        return _view(
            await self._accounts.execute(
                _user_id(), UpdateAccountInput(commit_name=None, commit_email=None, commit_use_account_email=False)
            )
        )
