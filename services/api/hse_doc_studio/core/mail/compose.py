"""Сборка письма: вид, язык и значения превращаются в тему, текст и HTML."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.mail.catalog import catalog, fill_text, format_duration, placeholders
from hse_doc_studio.core.mail.content import Action, Block, MailContent, Row, Text
from hse_doc_studio.core.mail.render import render_html, render_text

BRAND = "HSE Doc Studio"
_MAX_VALUE = 200
_MAX_SUBJECT = 150
_MAX_NOTE = 1000
_WHITESPACE = re.compile(r"\s+")


class MailTemplate(StrEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"  # noqa: S105 — вид письма, не пароль
    invite = "invite"
    email_change = "email_change"
    reset_notice = "reset_notice"
    passkey_added = "passkey_added"
    passkey_reset = "passkey_reset"
    project_invitation = "project_invitation"
    project_invitation_link = "project_invitation_link"
    access_request = "access_request"
    transfer_request = "transfer_request"
    smtp_test = "smtp_test"


# Путь на сервере, куда ведёт кнопка письма без своей ссылки.
_FIXED_PATH: dict[MailTemplate, str] = {
    MailTemplate.passkey_added: "/settings/account",
    MailTemplate.passkey_reset: "/settings/account",
    MailTemplate.project_invitation: "/inbox",
    MailTemplate.access_request: "/inbox",
    MailTemplate.transfer_request: "/inbox",
}


@dataclass(frozen=True)
class RenderedMail:
    subject: str
    text: str
    html: str


def resolve_lang(locale: str | None) -> Lang:
    """Язык письма: язык аккаунта получателя, иначе язык интерфейса запроса (у приглашения на адрес без аккаунта
    это язык приглашающего), иначе русский."""
    return Lang(locale) if locale in ("ru", "en") else current_interface_language()


def one_line(value: object, limit: int = _MAX_VALUE) -> str:
    """Значение для темы и коротких полей: без управляющих и форматирующих символов (переводы строк, bidi)."""
    kept = "".join(
        " " if ch.isspace() else ch for ch in str(value) if ch.isspace() or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    cleaned = _WHITESPACE.sub(" ", kept).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def clean_note(value: str) -> str:
    """Сообщение человека: переводы строк остаются, прочие управляющие и форматирующие символы убираются."""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    kept = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch) not in ("Cc", "Cf"))
    cleaned = re.sub(r"\n{3,}", "\n\n", kept).strip()
    return cleaned if len(cleaned) <= _MAX_NOTE else cleaned[: _MAX_NOTE - 1].rstrip() + "…"


def server_origin(server_url: str | None) -> str | None:
    """Публичный адрес установки без хвостового слэша; негодный (не http/https, с пробелами) отбрасывается."""
    if not server_url:
        return None
    url = server_url.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or any(ch.isspace() for ch in url):
        return None
    return url


def safe_link(link: str | None, server_url: str | None) -> str | None:
    """Ссылка для кнопки: только абсолютная http(s) на публичный адрес установки."""
    origin = server_origin(server_url)
    if not link or origin is None:
        return None
    candidate = link.strip()
    if any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf") for ch in candidate):
        return None
    return candidate if candidate == origin or candidate.startswith(f"{origin}/") else None


def _display_server(server_url: str | None) -> str:
    origin = server_origin(server_url)
    if origin is None:
        return BRAND
    parts = urlsplit(origin)
    return f"{parts.netloc}{parts.path}"


def _values(lang: Lang, to: str, server_url: str | None, extra: Mapping[str, object] | None) -> dict[str, str]:
    layout = catalog(lang)["layout"]
    roles = catalog(lang)["roles"]
    values = {str(key): one_line(value) for key, value in (extra or {}).items() if value is not None}
    values["email"] = one_line(to)
    values["server"] = _display_server(server_url)
    if not values.get("actor"):
        values["actor"] = layout["unknown_person"]
    if not values.get("project"):
        values["project"] = layout["unnamed_project"]
    if "role" in values:
        values["role"] = roles.get(values["role"], values["role"])
    return values


def _row(label: str, template: str, values: Mapping[str, str]) -> Row | None:
    """Строка сведений; без значения хотя бы одной подстановки строка пропускается."""
    if any(not values.get(name) for name in placeholders(template)):
        return None
    return Row(fill_text(label, values), fill_text(template, values))


def _expiry(lang: Lang, ttl: timedelta | None, expires_at: datetime | None, *, code: bool) -> str | None:
    layout = catalog(lang)["layout"]
    if ttl is not None:
        duration = format_duration(lang, int(ttl.total_seconds()))
        return fill_text(layout["code_valid_for" if code else "link_valid_for"], {"duration": duration})
    if expires_at is not None:
        return fill_text(
            layout["link_valid_until"], {"date": expires_at.astimezone(UTC).strftime(layout["date_format"])}
        )
    return None


def build_content(
    template: MailTemplate,
    lang: Lang,
    *,
    to: str,
    server_url: str | None,
    link: str | None = None,
    ttl: timedelta | None = None,
    expires_at: datetime | None = None,
    values: Mapping[str, object] | None = None,
    note: str | None = None,
    code: str | None = None,
) -> MailContent:
    cat = catalog(lang)
    layout = cat["layout"]
    texts = cat["mails"][template.value]
    vals = _values(lang, to, server_url, values)
    origin = server_origin(server_url)

    fixed = _FIXED_PATH.get(template)
    if fixed is not None:
        link = f"{origin}{fixed}" if origin else None
    href = safe_link(link, server_url)
    action = Action(texts["action"], href) if "action" in texts and href else None
    plain_link = None if href or not link else one_line(link, 500)

    def text(template_: str) -> Text:
        return Text(template_, vals)

    lead_key = "lead_by" if "lead_by" in texts and vals.get("inviter") else "lead"
    has_secret = action is not None or plain_link is not None or code is not None
    message = clean_note(note) if note else ""
    return MailContent(
        lang=lang,
        brand=BRAND,
        tagline=layout["tagline"],
        subject=one_line(fill_text(texts["subject"], vals), _MAX_SUBJECT),
        preheader=text(texts["preheader"]),
        title=text(texts["title"]),
        lead=text(texts[lead_key]),
        rows=tuple(r for label, tpl in texts.get("details", []) if (r := _row(label, tpl, vals)) is not None),
        action=action,
        plain_link=plain_link,
        code=one_line(code, 64) if code else None,
        expiry=_expiry(lang, ttl, expires_at, code=bool(code)) if has_secret else None,
        note=Block(fill_text(layout["note_title"], vals), message) if message else None,
        context_title=layout["context_title"],
        context=tuple(text(t) for t in texts.get("context", [])),
        security_title=layout["security_title"],
        security=tuple(text(t) for t in texts.get("security", [])),
        fallback_label=layout["fallback"],
        footer_server_label=layout["footer_server"],
        footer_recipient=fill_text(layout["footer_recipient"], vals),
        footer_auto=layout["footer_auto"],
        server_url=origin,
        server_display=_display_server(server_url),
    )


def compose(
    template: MailTemplate,
    lang: Lang,
    *,
    to: str,
    server_url: str | None,
    link: str | None = None,
    ttl: timedelta | None = None,
    expires_at: datetime | None = None,
    values: Mapping[str, object] | None = None,
    note: str | None = None,
    code: str | None = None,
) -> RenderedMail:
    """Тема, текст и HTML письма. `link` для видов с кнопкой; у уведомлений ссылка на сервер строится сама."""
    content = build_content(
        template,
        lang,
        to=to,
        server_url=server_url,
        link=link,
        ttl=ttl,
        expires_at=expires_at,
        values=values,
        note=note,
        code=code,
    )
    return RenderedMail(subject=content.subject, text=render_text(content), html=render_html(content))
