"""Перерисовка письма из журнала (docs/design/mail-log.md, L3..L5, срез B6): без ссылок и сообщений людей."""

from __future__ import annotations

import copy
import importlib
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail import MailTemplate, compose
from hse_doc_studio.core.mail.catalog import catalog
from hse_doc_studio.core.mail.compose import Redaction, fixed_path
from hse_doc_studio.core.mail.journal import (
    SAFE_VALUES,
    MailCause,
    MailLinkKind,
    MailLogEntry,
    MailOrigin,
    MailParams,
    MailRequest,
    MailStatus,
    rerender,
    rerendered,
    safe_params,
    template_digest,
)

compose_module = importlib.import_module("hse_doc_studio.core.mail.compose")

_SERVER = "https://studio.example.org"
_TOKEN = "Tk_known-secret-0123456789abcdef"  # noqa: S105 — известная строка теста, не секрет
_NOTE = "Личное сообщение: позвоните мне по номеру 8-900-000-00-00"
_PAGE = "/sign/5b0c1d2e-3f40-4152-8364-758697a8b9c0/0d1e2f30-4152-4637-8899-aabbccddeeff"
_VALUES = {
    "actor": "Анна Петрова",
    "inviter": "Анна Петрова",
    "project": "Курсовая работа по ГОСТ",
    "role": "editor",
    "profile": "Заявка на тему КП",
    "deadline": "15.11.2026, 23:59 (МСК)",
    "changed": "«Заявление»",
    "name": "MacBook, Touch ID",
    "count": "2",
    "signing": "ждём научного руководителя (Иван Сидоров)",
}
_CASES = [(template, lang) for template in MailTemplate for lang in Lang]
# Виды с кнопкой: только в них ссылка попадает в письмо (у остальных, например `smtp_test`, ссылки нет).
_LINKED = [(t, lang) for t, lang in _CASES if "action" in catalog(lang)["mails"][t.value]]
_HREF = re.compile(r'href="([^"]*)"')


def _hidden(lang: Lang, key: str) -> str:
    return str(catalog(lang)["layout"][key])


def _request(template: MailTemplate, lang: Lang, *, kind: MailLinkKind, note: str | None = None, **over: Any):
    link: str | None = None
    if kind is MailLinkKind.token:
        link = f"{_SERVER}/reset/{_TOKEN}"
    elif kind is MailLinkKind.page and fixed_path(template) is None:
        # Путь страницы уходит в журнал без запроса и якоря.
        link = f"{_SERVER}{_PAGE}?k={_TOKEN}#{_TOKEN}"
    fields: dict[str, Any] = {
        "template": template,
        "lang": lang,
        "to": "boris@example.org",
        "server_url": _SERVER,
        "origin": MailOrigin.notification,
        "link_kind": kind,
        "link": link,
        "ttl": timedelta(hours=1) if kind is not MailLinkKind.none else None,
        "values": {key: _VALUES[key] for key in SAFE_VALUES[template]},
        "note": note,
    }
    fields.update(over)
    return MailRequest(**fields)


def _entry(request: MailRequest, **over: Any) -> MailLogEntry:
    fields: dict[str, Any] = {
        "at": datetime(2026, 11, 11, 11, 32, tzinfo=UTC),
        "duration_ms": 10,
        "template": request.template.value,
        "lang": request.lang.value,
        "to_email": request.to,
        "subject": request.render().subject,
        "status": MailStatus.sent,
        "cause": MailCause.anonymous,
        "origin": request.origin.value,
        "params": safe_params(request),
        "template_digest": template_digest(request.template, request.lang),
        "message_id": "<1@studio.example.org>",
    }
    fields.update(over)
    return MailLogEntry(**fields)


def _kind(template: MailTemplate) -> MailLinkKind:
    return MailLinkKind.page if fixed_path(template) else MailLinkKind.token


@pytest.mark.parametrize(("template", "lang"), _CASES)
def test__rerender__every_template_and_language_without_link_or_note(template: MailTemplate, lang: Lang) -> None:
    request = _request(template, lang, kind=_kind(template), note=_NOTE)
    entry = _entry(request)

    mail = rerender(entry)

    assert mail is not None
    assert mail.subject == entry.subject
    for part in (mail.subject, mail.text, mail.html):
        assert _TOKEN not in part
        assert _NOTE not in part
    # Единственная ссылка в письме из журнала это адрес установки в подвале.
    assert set(_HREF.findall(mail.html)) <= {_SERVER}
    assert _hidden(lang, "note_hidden") in mail.text
    assert _hidden(lang, "note_hidden") in mail.html
    assert rerendered(entry) is False


@pytest.mark.parametrize(("template", "lang"), [(t, lang) for t, lang in _LINKED if fixed_path(t) is None])
def test__rerender__token_link_is_hidden_and_the_rest_matches_the_sent_mail(template: MailTemplate, lang: Lang) -> None:
    request = _request(template, lang, kind=MailLinkKind.token)
    sent = request.render()

    mail = rerender(_entry(request))

    assert mail is not None
    hidden = _hidden(lang, "link_hidden")
    assert hidden in mail.text
    assert hidden in mail.html
    assert mail.text == sent.text.replace(f"{_SERVER}/reset/{_TOKEN}", hidden)


@pytest.mark.parametrize(("template", "lang"), _LINKED)
def test__rerender__page_link_shows_its_path_as_text(template: MailTemplate, lang: Lang) -> None:
    request = _request(template, lang, kind=MailLinkKind.page)
    sent = request.render()
    path = fixed_path(template) or _PAGE

    mail = rerender(_entry(request))

    assert mail is not None
    assert path in mail.text
    assert f">{path}<" in mail.html
    assert _hidden(lang, "link_hidden") not in mail.text
    live_link = f"{_SERVER}{path}" if fixed_path(template) else f"{_SERVER}{_PAGE}?k={_TOKEN}#{_TOKEN}"
    assert mail.text == sent.text.replace(live_link, path)


@pytest.mark.parametrize(("template", "lang"), _CASES)
def test__rerender__a_row_without_values_still_renders(template: MailTemplate, lang: Lang) -> None:
    """Старая строка может не знать подстановку, которая появилась в шаблоне позже: карточка не падает."""
    request = _request(template, lang, kind=_kind(template))
    entry = _entry(request, params=replace(safe_params(request), values={}))

    mail = rerender(entry)

    assert mail is not None
    assert "{" not in mail.subject


def test__rerender__button_keeps_its_label_but_has_no_address() -> None:
    mail = rerender(_entry(_request(MailTemplate.reset_password, Lang.ru, kind=MailLinkKind.token)))

    assert mail is not None
    label = catalog(Lang.ru)["mails"]["reset_password"]["action"]
    assert re.search(rf'<span class="e-btn-a"[^>]*>{re.escape(label)}</span>', mail.html)
    assert f">{label}</a>" not in mail.html


def test__rerender__without_public_address_the_hidden_link_stands_as_text() -> None:
    request = _request(MailTemplate.reset_password, Lang.ru, kind=MailLinkKind.token)
    entry = _entry(request, params=replace(safe_params(request), server=None))

    mail = rerender(entry)

    assert mail is not None
    assert 'class="e-btn-a"' not in mail.html
    assert _hidden(Lang.ru, "link_hidden") in mail.text
    assert _HREF.findall(mail.html) == []


def test__rerender__expiry_comes_from_the_stored_term() -> None:
    request = _request(
        MailTemplate.project_invitation_link,
        Lang.ru,
        kind=MailLinkKind.token,
        ttl=None,
        expires_at=datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
    )

    mail = rerender(_entry(request))

    assert mail is not None
    assert "Ссылка действует до 10.11.2026, 17:30 (МСК)." in mail.text


def test__rerender__a_mail_without_a_link_has_no_link_line() -> None:
    request = _request(MailTemplate.smtp_test, Lang.en, kind=MailLinkKind.none)

    mail = rerender(_entry(request))

    assert mail is not None
    assert mail.text == request.render().text
    assert _hidden(Lang.en, "link_hidden") not in mail.text


def test__rerender__a_removed_template_or_language_has_no_preview() -> None:
    entry = _entry(_request(MailTemplate.reset_password, Lang.ru, kind=MailLinkKind.token))

    assert rerender(replace(entry, template="weekly_digest")) is None
    assert rerendered(replace(entry, template="weekly_digest")) is False
    assert rerender(replace(entry, lang="de")) is None


def test__rerender__params_read_back_from_json_give_the_same_mail() -> None:
    request = _request(MailTemplate.signing_reminder, Lang.en, kind=MailLinkKind.page, note=_NOTE)
    entry = _entry(request)
    stored = replace(entry, params=MailParams.from_json(entry.params.to_json()))

    assert rerender(stored) == rerender(entry)


def test__rerendered__after_the_texts_change(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _entry(_request(MailTemplate.reset_password, Lang.ru, kind=MailLinkKind.token))
    edited = copy.deepcopy(dict(catalog(Lang.ru)))
    edited["mails"]["reset_password"]["lead"] += " Новая фраза."

    def patched(lang: Lang) -> Mapping[str, Any]:
        return edited if lang is Lang.ru else catalog(lang)

    monkeypatch.setattr(compose_module, "catalog", patched)
    template_digest.cache_clear()
    try:
        mail = rerender(entry)
        assert rerendered(entry) is True
        assert mail is not None
        assert "Новая фраза." in mail.text
    finally:
        template_digest.cache_clear()


def test__compose__redaction_takes_no_link_and_no_note() -> None:
    with pytest.raises(ValueError, match="no link"):
        compose(
            MailTemplate.reset_password,
            Lang.ru,
            to="a@example.org",
            server_url=_SERVER,
            link=f"{_SERVER}/reset/x",
            redaction=Redaction(token_link=True),
        )
    with pytest.raises(ValueError, match="no note"):
        compose(
            MailTemplate.reset_password,
            Lang.ru,
            to="a@example.org",
            server_url=_SERVER,
            note="hi",
            redaction=Redaction(token_link=True),
        )
