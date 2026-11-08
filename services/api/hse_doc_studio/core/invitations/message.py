"""Готовый текст приглашения в проект: собирается по шаблону из данных проекта, без ИИ.

Каждая фраза берётся, только если для неё есть данные: без имени приглашаемого обращение без имени, без группы
подпись без группы, без вида работы и комплекта документов этих фраз нет. Тексты лежат в `locales/<язык>.json`
рядом с модулем, подстановка за один проход (`{x}` в названии проекта остаётся текстом). Текст не длиннее
`MESSAGE_MAX`: при нехватке места первыми уходят список документов, вид работы и тема.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.invitations.entities import MESSAGE_MAX, SUPERVISOR_PERSONAS
from hse_doc_studio.core.mail.catalog import fill_text
from hse_doc_studio.core.mail.compose import one_line

_LOCALES = Path(__file__).with_name("locales")
AUTHOR_PERSONA = "author"
_NAME_MAX = 120
_TITLE_MAX = 300
_DOC_MAX = 120
_MAX_DOCUMENTS = 12


@lru_cache(maxsize=len(Lang))
def message_catalog(lang: Lang) -> Mapping[str, Any]:
    return json.loads((_LOCALES / f"{lang.value}.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ProjectPerson:
    """Человек из `project.json`: автор (почта, группа, слаг) или руководитель (только имя)."""

    name: str
    email: str | None = None
    group: str | None = None
    slug: str | None = None


@dataclass(frozen=True)
class InvitationFacts:
    """Что известно о проекте для текста приглашения. Названия шаблона и документов уже на языке текста."""

    project_name: str
    topic: str | None = None
    work_kind: str | None = None
    documents: tuple[str, ...] = ()
    authors: tuple[ProjectPerson, ...] = ()
    # Персона руководителя (`supervisor`, `co_supervisor`, `academic_supervisor`) -> человек из проекта.
    supervisors: Mapping[str, ProjectPerson] = field(default_factory=dict)


@dataclass(frozen=True)
class MessageRequest:
    """Кого и кто приглашает: роль доступа, персона из формы, почта приглашаемого и аккаунт приглашающего."""

    role: Role
    persona: str | None = None
    invitee_email: str | None = None
    inviter_name: str | None = None
    inviter_email: str | None = None


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = one_line(value, limit)
    return cleaned or None


def _same_email(a: str | None, b: str | None) -> bool:
    return bool(a and b) and normalize_email(str(a)) == normalize_email(str(b))


def _same_name(a: str | None, b: str | None) -> bool:
    return bool(a and b) and " ".join(str(a).split()).casefold() == " ".join(str(b).split()).casefold()


def invitee_of(
    facts: InvitationFacts, persona: str | None, email: str | None
) -> tuple[ProjectPerson | None, str | None]:
    """Приглашаемый среди людей проекта и его роль в работе: по персоне из формы, иначе по почте автора."""
    if persona in SUPERVISOR_PERSONAS:
        return facts.supervisors.get(str(persona)), persona
    if persona:
        author = next((a for a in facts.authors if a.slug == persona), None)
        return (author, AUTHOR_PERSONA) if author is not None else (None, None)
    author = next((a for a in facts.authors if _same_email(a.email, email)), None)
    return (author, AUTHOR_PERSONA) if author is not None else (None, None)


def inviter_group(facts: InvitationFacts, name: str | None, email: str | None) -> str | None:
    """Группа приглашающего: у автора проекта с его почтой, иначе с его именем."""
    author = next((a for a in facts.authors if _same_email(a.email, email)), None)
    if author is None:
        author = next((a for a in facts.authors if _same_name(a.name, name)), None)
    return author.group if author is not None else None


def _lower_first(text: str) -> str:
    """«Отчёт о КП» -> «отчёт о КП» внутри фразы; аббревиатуры («КП», «ВКР») не трогаются."""
    if len(text) > 1 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text


@dataclass(frozen=True)
class _Parts:
    greeting: str
    invite: str
    topic: str | None
    work_kind: str | None
    access_with_docs: str
    access_plain: str
    closing: tuple[str, ...]

    def render(self, *, topic: bool, work_kind: bool, documents: bool) -> str:
        body = [self.invite]
        if topic and self.topic:
            body.append(self.topic)
        if work_kind and self.work_kind:
            body.append(self.work_kind)
        body.append(self.access_with_docs if documents else self.access_plain)
        blocks = [self.greeting, " ".join(body)]
        if self.closing:
            blocks.append("\n".join(self.closing))
        return "\n\n".join(blocks)


def compose_invitation_message(facts: InvitationFacts, request: MessageRequest, lang: Lang) -> str:
    """Текст приглашения на языке `lang`: обращение, приглашение с ролью, о работе, что можно делать, подпись."""
    cat = message_catalog(lang)
    person, persona_kind = invitee_of(facts, request.persona, request.invitee_email)
    invitee_name = _clean(person.name if person else None, _NAME_MAX)
    project = _clean(facts.project_name, _TITLE_MAX) or ""
    role_key = persona_kind or request.role.value
    role_words = cat["role"].get(role_key)
    invite = (
        fill_text(cat["invite_as"], {"project": project, "role": role_words})
        if role_words
        else fill_text(cat["invite"], {"project": project})
    )
    topic = _clean(facts.topic, _TITLE_MAX)
    if topic is not None and _same_name(topic, facts.project_name):
        topic = None
    kind = _clean(facts.work_kind, _TITLE_MAX)
    if kind is not None and lang is Lang.ru:
        kind = _lower_first(kind)
    docs = [d for d in (_clean(x, _DOC_MAX) for x in facts.documents[:_MAX_DOCUMENTS]) if d]
    if lang is Lang.ru:
        docs = [_lower_first(d) for d in docs]
    access = cat["access"].get(request.role.value, cat["access"]["reader"])
    docs_part = fill_text(cat["documents"], {"documents": ", ".join(docs)}) if docs else ""
    inviter = _clean(request.inviter_name, _NAME_MAX)
    group = _clean(inviter_group(facts, request.inviter_name, request.inviter_email), _NAME_MAX)
    closing: tuple[str, ...] = ()
    if inviter:
        signature = (
            fill_text(cat["signature_group"], {"name": inviter, "group": group})
            if group
            else fill_text(cat["signature"], {"name": inviter})
        )
        closing = (cat["closing"], signature)
    parts = _Parts(
        greeting=fill_text(cat["greeting_named"], {"name": invitee_name}) if invitee_name else cat["greeting"],
        invite=invite,
        topic=fill_text(cat["topic"], {"topic": topic}) if topic else None,
        work_kind=fill_text(cat["work_kind"], {"kind": kind}) if kind else None,
        access_with_docs=fill_text(access, {"documents": docs_part}),
        access_plain=fill_text(access, {"documents": ""}),
        closing=closing,
    )
    # Длинные названия: сначала без списка документов, затем без вида работы и темы.
    for flags in ((True, True, True), (True, True, False), (True, False, False), (False, False, False)):
        text = parts.render(topic=flags[0], work_kind=flags[1], documents=flags[2])
        if len(text) <= MESSAGE_MAX:
            return text
    return text[: MESSAGE_MAX - 1].rstrip() + "…"
