"""Профиль аккаунта: имя, язык и подпись коммитов человека."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from enum import Enum
from functools import partial
from typing import Any

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.commit_identity import CommitIdentity, commit_identity
from hse_doc_studio.core.identity.entities import User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.vcs.author import normalize_email, normalize_name
from hse_doc_studio.core.vcs.errors import ProfileInvalidError, ProfileValidationError

ACCOUNT_NAME_MAX = 200
LOCALES = frozenset({"ru", "en"})


class _Unset(Enum):
    unset = "unset"


UNSET = _Unset.unset


@dataclass(frozen=True)
class AccountView:
    user: User
    identity: CommitIdentity


@dataclass(frozen=True)
class UpdateAccountInput:
    """Поля, которых нет в запросе, остаются как есть; `None` у commit_* сбрасывает значение."""

    name: str | None | _Unset = UNSET
    locale: str | None | _Unset = UNSET
    commit_name: str | None | _Unset = UNSET
    commit_email: str | None | _Unset = UNSET
    commit_use_account_email: bool | _Unset = UNSET


def _blank_to_none(value: str | None) -> str | None:
    return value if value and value.strip() else None


def _account_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise ProfileValidationError("name", "required", localized_error("Укажи имя.", "Enter a name."))
    if len(name) > ACCOUNT_NAME_MAX:
        raise ProfileValidationError(
            "name",
            "too_long",
            localized_error(
                f"Имя длиннее {ACCOUNT_NAME_MAX} символов.", f"The name is longer than {ACCOUNT_NAME_MAX} characters."
            ),
        )
    return name


def _commit_field(field: str, normalize: Callable[[str], str], raw: str | None) -> str | None:
    """Пустое значение сбрасывает своё; ошибка правила уходит под именем поля подписи, а не имени аккаунта."""
    value = _blank_to_none(raw)
    if value is None:
        return None
    try:
        return normalize(value)
    except ProfileValidationError as exc:
        raise ProfileValidationError(field, exc.reason, exc.message) from exc


def _locale(raw: str | None) -> str | None:
    if raw is not None and raw not in LOCALES:
        raise ProfileValidationError(
            "locale", "invalid", localized_error("Язык не поддерживается.", "The language is not supported.")
        )
    return raw


_CHECKS: dict[str, Callable[[Any], object]] = {
    "name": _account_name,
    "locale": _locale,
    "commit_name": partial(_commit_field, "commit_name", normalize_name),
    "commit_email": partial(_commit_field, "commit_email", normalize_email),
    "commit_use_account_email": bool,
}


def _apply(user: User, inp: UpdateAccountInput) -> User:
    """Новая версия пользователя; негодные поля собираются вместе, как у профиля автора."""
    errors: list[ProfileValidationError] = []
    changes: dict[str, object] = {}
    for f in fields(inp):
        value = getattr(inp, f.name)
        if isinstance(value, _Unset):
            continue
        try:
            changes[f.name] = _CHECKS[f.name](value)
        except ProfileValidationError as exc:
            errors.append(exc)
    if errors:
        raise ProfileInvalidError(errors)
    return replace(user, **changes)  # type: ignore[arg-type]


class GetAccountUC:
    def __init__(self, users: IUserRepository, noreply_domain: str) -> None:
        self._users = users
        self._domain = noreply_domain

    async def execute(self, user_id: str) -> AccountView:
        user = await self._users.get(user_id)
        if user is None:
            raise IdentityError(IdentityErrorCode.auth_required)
        return AccountView(user, commit_identity(user, self._domain))


class UpdateAccountUC:
    def __init__(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork, noreply_domain: str) -> None:
        self._users = users
        self._audit = audit
        self._uow = uow
        self._domain = noreply_domain

    async def execute(self, user_id: str, inp: UpdateAccountInput) -> AccountView:
        async with self._uow.begin():
            user = await self._users.get_for_update(user_id)
            if user is None:
                raise IdentityError(IdentityErrorCode.auth_required)
            updated = _apply(user, inp)
            if updated != user:
                await self._users.update(updated)
                changed = sorted(f.name for f in fields(inp) if not isinstance(getattr(inp, f.name), _Unset))
                await self._audit.record("account.profile_updated", actor_id=user_id, details={"fields": changed})
        return AccountView(updated, commit_identity(updated, self._domain))
