"""Кем подписываются коммиты человека на сервере.

Адрес из аккаунта по умолчанию наружу не уходит: коммит навсегда остаётся во внешних remote, поэтому
подпись берёт сгенерированный noreply-адрес. Настоящий адрес попадает в коммиты только по желанию
человека: либо флаг «использовать e-mail аккаунта», либо собственный адрес для коммитов.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from hse_doc_studio.core.identity.entities import User

NOREPLY_LABEL = "noreply"
DEFAULT_NOREPLY_DOMAIN = f"{NOREPLY_LABEL}.localhost"


@dataclass(frozen=True)
class CommitIdentity:
    name: str
    email: str
    is_noreply: bool


def noreply_domain(public_url: str | None) -> str:
    """Домен noreply-адреса: хост внешнего адреса Студии, без него localhost."""
    host = urlsplit(public_url or "").hostname if public_url else None
    return f"{NOREPLY_LABEL}.{host}" if host else DEFAULT_NOREPLY_DOMAIN


def noreply_email(user_id: str, domain: str) -> str:
    return f"{user_id}@{domain}"


def commit_identity(user: User, domain: str) -> CommitIdentity:
    """Подпись по правилам: свой адрес для коммитов, затем e-mail аккаунта по согласию, иначе noreply."""
    name = user.commit_name or user.name
    if user.commit_email:
        return CommitIdentity(name, user.commit_email, is_noreply=False)
    if user.commit_use_account_email:
        return CommitIdentity(name, user.email, is_noreply=False)
    return CommitIdentity(name, noreply_email(user.id, domain), is_noreply=True)


def guest_commit_identity(name: str | None, link_id: str, label: str, domain: str) -> CommitIdentity:
    """Подпись правок гостя по ссылке: «Гость: Борис (ссылка «Для группы»)», адрес `guest+<ссылка>@noreply`."""
    who = name or "без имени"
    return CommitIdentity(f"Гость: {who} (ссылка «{label}»)", f"guest+{link_id}@{domain}", is_noreply=True)
