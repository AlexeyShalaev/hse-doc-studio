from __future__ import annotations

import re

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.vcs.entities import VcsAuthor

_MAX_NAME = 128
_MAX_EMAIL = 254
# git обрезает эти символы по краям имени и отказывается от имени, где ничего больше нет.
_GIT_CRUD = " \t.,:;<>\"'\\"
_EMAIL = re.compile(r"[^@\s<>]+@[^@\s<>]+")


def _has_control(value: str) -> bool:
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _clean_name(name: str | None) -> str | None:
    name = (name or "").strip()
    if not name or len(name) > _MAX_NAME:
        return None
    if "<" in name or ">" in name or _has_control(name):
        return None
    if not name.strip(_GIT_CRUD):
        return None
    return name


def _clean_email(email: str | None) -> str | None:
    email = (email or "").strip()
    if len(email) > _MAX_EMAIL or _has_control(email):
        return None
    return email if _EMAIL.fullmatch(email) else None


class ActorCommitAuthorProvider:
    """Подпись коммита берётся у актора запроса; во всех остальных случаях служебная.

    Локальный актор, отсутствие запроса (восстановление при старте) и актор с именем
    или e-mail, которые git не примет, дают `fallback`, поэтому коммит не падает.
    """

    def __init__(self, fallback: VcsAuthor) -> None:
        self._fallback = fallback

    def author(self) -> VcsAuthor:
        actor = current_actor()
        if actor is None or actor.kind is ActorKind.local:
            return self._fallback
        name = _clean_name(actor.name)
        email = _clean_email(actor.email)
        if name is None or email is None:
            return self._fallback
        return VcsAuthor(name, email)
