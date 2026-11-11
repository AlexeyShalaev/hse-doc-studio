"""Журнал писем, контракт (docs/design/mail-log.md, B1): белый список значений, безопасные параметры, отпечаток."""

from __future__ import annotations

import copy
import importlib
import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail import MailTemplate, compose, journal
from hse_doc_studio.core.mail.catalog import catalog, placeholders
from hse_doc_studio.core.mail.compose import fixed_path
from hse_doc_studio.core.mail.journal import (
    REASONS_BY_STATUS,
    SAFE_VALUE_KEYS,
    SAFE_VALUES,
    MailCause,
    MailFailureClass,
    MailLinkKind,
    MailLogEntry,
    MailLogQuery,
    MailOrigin,
    MailParams,
    MailRequest,
    MailSkipReason,
    MailStatus,
    known_template,
    safe_params,
    template_digest,
)

# Модуль, а не одноимённая функция из `core.mail`: подменяем словарь, которым он собирает письма.
compose_module = importlib.import_module("hse_doc_studio.core.mail.compose")

_SERVER = "https://studio.example.org"
_TOKEN = "Tk_known-secret-0123456789abcdef"  # noqa: S105 — известная строка теста, не секрет
_NOTE = "Личное сообщение: позвоните мне по номеру 8-900-000-00-00"
# Подстановки, которые сами не значения шаблона: адрес получателя и адрес установки хранятся отдельно.
_NOT_VALUES = {"email", "server"}
# L3: список значений, согласованный в дизайне.
_L3 = {"actor", "inviter", "project", "role", "profile", "deadline", "changed", "name", "count"}


def _strings(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _mail_placeholders(template: MailTemplate, lang: Lang) -> set[str]:
    return {name for text in _strings(catalog(lang)["mails"][template.value]) for name in placeholders(text)}


def _link_kind(template: MailTemplate) -> MailLinkKind:
    if fixed_path(template):
        return MailLinkKind.page
    if template.value.startswith("signing_"):
        return MailLinkKind.page
    if template in (MailTemplate.reset_notice, MailTemplate.smtp_test):
        return MailLinkKind.none
    return MailLinkKind.token


def _request(template: MailTemplate, lang: Lang = Lang.ru, **over: Any) -> MailRequest:
    kind = _link_kind(template)
    link = {
        MailLinkKind.token: f"{_SERVER}/reset/{_TOKEN}",
        MailLinkKind.page: None if fixed_path(template) else f"{_SERVER}/sign/p1/r1?from={_TOKEN}#{_TOKEN}",
        MailLinkKind.none: None,
    }[kind]
    fields: dict[str, Any] = {
        "template": template,
        "lang": lang,
        "to": "anna.petrova@example.org",
        "server_url": _SERVER,
        "origin": MailOrigin.notification,
        "link_kind": kind,
        "link": link,
        "ttl": timedelta(hours=1) if kind is MailLinkKind.token else None,
        "values": {key: f"value of {key}" for key in _L3} | {"link": _TOKEN, "token": _TOKEN, "code": _TOKEN},
        "note": _NOTE,
    }
    fields.update(over)
    return MailRequest(**fields)


# --- белый список ---


def test__safe_values__cover_every_template() -> None:
    assert set(SAFE_VALUES) == set(MailTemplate)


@pytest.mark.parametrize("lang", list(Lang))
@pytest.mark.parametrize("template", list(MailTemplate))
def test__safe_values__are_exactly_the_placeholders_of_the_mail_texts(template: MailTemplate, lang: Lang) -> None:
    # Новая подстановка в словаре письма без решения в белом списке не пройдёт: значение либо попадёт в журнал
    # осознанно, либо письмо в карточке перерисуется без него.
    assert _mail_placeholders(template, lang) - _NOT_VALUES == set(SAFE_VALUES[template])


def test__safe_value_keys__match_the_design_list_and_none_looks_like_a_secret() -> None:
    assert set(SAFE_VALUE_KEYS) == _L3
    secretish = re.compile(r"link|url|token|code|secret|password|key|note|message|email")
    assert [key for key in SAFE_VALUE_KEYS if secretish.search(key)] == []


def test__layout_placeholders__are_not_template_values() -> None:
    # Подстановки оформления (срок, дата, адрес) считает сам шаблон: в журнал они не идут значениями.
    for lang in Lang:
        layout = {name for text in _strings(catalog(lang)["layout"]) for name in placeholders(text)}
        assert layout & SAFE_VALUE_KEYS == set()


# --- безопасные параметры ---


@pytest.mark.parametrize("template", list(MailTemplate))
def test__safe_params__never_keep_the_token_or_the_note(template: MailTemplate) -> None:
    params = safe_params(_request(template))
    dumped = json.dumps(params.to_json(), ensure_ascii=False)

    assert _TOKEN not in dumped
    assert "8-900" not in dumped
    assert set(params.values) == set(SAFE_VALUES[template])
    assert params.note_len == len(_NOTE)


def test__safe_params__token_link_keeps_only_its_kind_and_ttl() -> None:
    params = safe_params(_request(MailTemplate.reset_password))

    assert params.link is MailLinkKind.token
    assert params.link_path is None
    assert params.ttl_s == 3600
    assert params.server == _SERVER
    assert params.values == {}


def test__safe_params__page_link_keeps_the_path_without_query_and_fragment() -> None:
    params = safe_params(_request(MailTemplate.signing_request))

    assert params.link is MailLinkKind.page
    assert params.link_path == "/sign/p1/r1"


def test__safe_params__fixed_page_comes_from_the_template() -> None:
    params = safe_params(_request(MailTemplate.project_invitation))

    assert params.link is MailLinkKind.page
    assert params.link_path == "/inbox"


def test__safe_params__values_are_one_line_and_none_is_dropped() -> None:
    request = _request(MailTemplate.project_invitation, values={"actor": "Анна\n‮Petrova", "role": None})

    assert safe_params(request).values == {"actor": "Анна Petrova"}


def test__safe_params__expiry_note_and_bad_server() -> None:
    expires = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)
    request = _request(
        MailTemplate.project_invitation_link,
        expires_at=expires,
        ttl=None,
        note=None,
        server_url="javascript:alert(1)",
    )

    params = safe_params(request)

    assert params.expires_at == expires
    assert params.ttl_s is None
    assert params.note_len == 0
    assert params.server is None


def test__mail_params__round_trip_through_json() -> None:
    params = safe_params(_request(MailTemplate.project_invitation_link, expires_at=datetime(2026, 11, 18, tzinfo=UTC)))

    assert MailParams.from_json(json.loads(json.dumps(params.to_json()))) == params


def test__mail_params__from_json_drops_what_is_not_safe() -> None:
    raw = {
        "values": {"actor": "Анна", "link": _TOKEN, "count": 2},
        "link": "magic",
        "link_path": "/sign/x",
        "ttl_s": True,
        "note_len": "12",
        "server": 5,
        "body": "<html>",
    }

    params = MailParams.from_json(raw)

    assert params == MailParams(values={"actor": "Анна"})


def test__mail_params__page_path_is_read_only_for_page_links() -> None:
    assert MailParams.from_json({"link": "page", "link_path": "/inbox"}).link_path == "/inbox"
    assert MailParams.from_json({"link": "token", "link_path": "/reset/x"}).link_path is None


# --- запрос ---


def test__request__render_is_the_mail_as_sent() -> None:
    request = _request(MailTemplate.reset_password)

    assert request.render() == compose(
        MailTemplate.reset_password,
        Lang.ru,
        to=request.to,
        server_url=_SERVER,
        link=request.link,
        ttl=request.ttl,
        values=request.values,
        note=request.note,
    )
    assert _TOKEN in request.render().text


@pytest.mark.parametrize(
    ("template", "over", "error"),
    [
        (MailTemplate.reset_password, {"link_kind": MailLinkKind.token, "link": None}, "needs the link"),
        (MailTemplate.smtp_test, {"link_kind": MailLinkKind.none, "link": f"{_SERVER}/x"}, "carries a link"),
        (MailTemplate.project_invitation, {"link_kind": MailLinkKind.none, "link": None}, "carries a link"),
        (MailTemplate.passkey_added, {"link_kind": MailLinkKind.token, "link": f"{_SERVER}/x"}, "fixed page"),
        (MailTemplate.signing_request, {"ref_kind": journal.MailRefKind.signing_route}, "go together"),
    ],
)
def test__request__rejects_inconsistent_links_and_refs(
    template: MailTemplate, over: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        _request(template, **over)


# --- отпечаток шаблона ---


@pytest.mark.parametrize("lang", list(Lang))
@pytest.mark.parametrize("template", list(MailTemplate))
def test__template_digest__is_16_hex_and_stable(template: MailTemplate, lang: Lang) -> None:
    digest = template_digest(template, lang)

    assert re.fullmatch(r"[0-9a-f]{16}", digest)
    template_digest.cache_clear()
    assert template_digest(template, lang) == digest


def test__template_digest__differs_by_template_and_language() -> None:
    digests = {template_digest(t, lang) for t in MailTemplate for lang in Lang}

    assert len(digests) == len(MailTemplate) * len(Lang)


def test__template_digest__changes_when_the_texts_change(monkeypatch: pytest.MonkeyPatch) -> None:
    before = template_digest(MailTemplate.reset_password, Lang.ru)
    other = template_digest(MailTemplate.reset_password, Lang.en)
    edited = copy.deepcopy(dict(catalog(Lang.ru)))
    edited["mails"]["reset_password"]["lead"] += " Новая фраза."

    def patched(lang: Lang) -> Mapping[str, Any]:
        return edited if lang is Lang.ru else catalog(lang)

    monkeypatch.setattr(compose_module, "catalog", patched)
    template_digest.cache_clear()
    try:
        assert template_digest(MailTemplate.reset_password, Lang.ru) != before
        assert template_digest(MailTemplate.reset_password, Lang.en) == other
    finally:
        template_digest.cache_clear()


# --- строка журнала и итоги ---


def _entry(**over: Any) -> MailLogEntry:
    fields: dict[str, Any] = {
        "at": datetime(2026, 11, 11, 11, 32, tzinfo=UTC),
        "duration_ms": 388,
        "template": "reset_password",
        "lang": "ru",
        "to_email": "boris@example.org",
        "subject": "Сброс пароля",
        "status": MailStatus.sent,
        "cause": MailCause.anonymous,
        "origin": MailOrigin.forgot_password,
        "params": MailParams(link=MailLinkKind.token, ttl_s=3600),
        "template_digest": "0123456789abcdef",
        "message_id": "<1@studio.example.org>",
    }
    fields.update(over)
    return MailLogEntry(**fields)


def test__entry__sent_needs_message_id() -> None:
    with pytest.raises(ValueError, match="Message-ID"):
        _entry(message_id=None)
    assert _entry(status=MailStatus.failed, message_id=None, reason="auth").id is None


def test__entry__template_known_survives_a_removed_kind() -> None:
    assert _entry().template_known
    assert not _entry(template="weekly_digest").template_known
    assert known_template("reset_password") is MailTemplate.reset_password
    assert known_template("weekly_digest") is None


def test__reasons_by_status__follow_the_design() -> None:
    assert set(REASONS_BY_STATUS) == set(MailStatus)
    assert REASONS_BY_STATUS[MailStatus.sent] == frozenset()
    assert REASONS_BY_STATUS[MailStatus.failed] == set(MailFailureClass)
    assert REASONS_BY_STATUS[MailStatus.not_sent] == {MailSkipReason.smtp_off}
    assert MailSkipReason.smtp_off not in REASONS_BY_STATUS[MailStatus.suppressed]


def test__query__filtered_only_with_a_filter() -> None:
    assert not MailLogQuery(before_id=10, limit=20).filtered
    assert MailLogQuery(statuses=(MailStatus.failed,)).filtered
    assert MailLogQuery(q="anna").filtered


def test__codes__fit_their_columns() -> None:
    assert all(len(t.value) <= journal.TEMPLATE_MAX for t in MailTemplate)
    assert all(len(o.value) <= journal.ORIGIN_MAX for o in MailOrigin)
    assert all(len(r.value) <= 32 for r in [*MailFailureClass, *MailSkipReason])
    assert all(len(k.value) <= 32 for k in journal.MailRefKind)
