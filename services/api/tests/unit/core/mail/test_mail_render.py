"""Письма Студии: рендер каждого вида на ru и en, экранирование, тема, ссылки и выбор языка."""

from __future__ import annotations

import re
from datetime import timedelta
from html.parser import HTMLParser

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.mail import MailTemplate, compose, resolve_lang
from hse_doc_studio.core.mail.catalog import format_duration
from hse_doc_studio.core.mail.samples import SAMPLE_RECIPIENT, SAMPLE_SERVER, sample_mail

ALL = [(t, lang) for t in MailTemplate for lang in Lang]
_PLACEHOLDER = re.compile(r"\{\w+\}")
_DASHES_AND_ARROWS = ("—", "–", "→", "←", "⇒", "->", "<-", "=>")
_EVIL = '<script>alert("x")</script> & "q" \'s\' {not_a_placeholder}'


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.hrefs: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend(attrs)
        self.hrefs.extend(v for k, v in attrs if k == "href" and v)


def _parsed(html: str) -> _Collector:
    parser = _Collector()
    parser.feed(html)
    return parser


@pytest.mark.parametrize(("template", "lang"), ALL)
def test__every_mail__has_subject_text_html_without_leftovers(template: MailTemplate, lang: Lang) -> None:
    mail = sample_mail(template, lang)

    assert mail.subject
    assert "\n" not in mail.subject
    assert "\r" not in mail.subject
    for part in (mail.subject, mail.text, mail.html):
        assert not _PLACEHOLDER.search(part), part
        assert not any(mark in part for mark in _DASHES_AND_ARROWS)
    assert f'<html lang="{lang.value}">' in mail.html
    assert mail.text.endswith("\n")
    assert SAMPLE_SERVER in mail.text


@pytest.mark.parametrize(("template", "lang"), ALL)
def test__every_mail__html_is_email_safe(template: MailTemplate, lang: Lang) -> None:
    html = sample_mail(template, lang).html
    parsed = _parsed(html)

    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert "link" not in parsed.tags
    assert "iframe" not in parsed.tags
    assert not [v for k, v in parsed.attrs if k in {"src", "background"}]
    assert "url(" not in html
    assert "@import" not in html
    assert "prefers-color-scheme:dark" in html
    assert "max-width:620px" in html
    assert 'name="viewport"' in html
    assert 'name="color-scheme"' in html
    assert all(href.startswith(SAMPLE_SERVER) for href in parsed.hrefs)
    assert 'role="presentation"' in html


@pytest.mark.parametrize(("template", "lang"), ALL)
def test__every_mail__html_has_title_context_and_footer(template: MailTemplate, lang: Lang) -> None:
    mail = sample_mail(template, lang)

    assert "<h1" in mail.html
    assert "studio.example.org" in mail.html
    assert SAMPLE_RECIPIENT in mail.html
    assert "HSE Doc Studio" in mail.html


@pytest.mark.parametrize("lang", list(Lang))
@pytest.mark.parametrize("template", [t for t in MailTemplate if t.value.endswith(("password", "email", "invite"))])
def test__link_mails__have_button_fallback_link_and_expiry(template: MailTemplate, lang: Lang) -> None:
    mail = sample_mail(template, lang)

    parsed = _parsed(mail.html)
    assert len(parsed.hrefs) >= 3
    link = next(line for line in mail.text.splitlines() if line.startswith(SAMPLE_SERVER + "/"))
    assert mail.text.count(link) == 1
    assert mail.html.count(link) >= 2
    assert re.search(r"\d", mail.text.split(link)[1].splitlines()[2])


def test__password_reset__ru_fragments() -> None:
    mail = sample_mail(MailTemplate.reset_password, Lang.ru)

    assert mail.subject == "Сброс пароля"
    assert "Задать новый пароль" in mail.html
    assert "Ссылка действует 1 час." in mail.text
    assert "пароль останется прежним" in mail.text
    assert "Безопасность" in mail.html


def test__password_reset__en_fragments() -> None:
    mail = sample_mail(MailTemplate.reset_password, Lang.en)

    assert mail.subject == "Password reset"
    assert "Set a new password" in mail.html
    assert "The link is valid for 1 hour." in mail.text
    assert "your password stays the same" in mail.text
    assert "Security" in mail.html


def test__verify_email__valid_for_48_hours_reads_as_two_days() -> None:
    assert "Ссылка действует 2 дня." in sample_mail(MailTemplate.verify_email, Lang.ru).text
    assert "The link is valid for 2 days." in sample_mail(MailTemplate.verify_email, Lang.en).text


def test__invite__names_the_inviter_when_known_and_skips_the_row_when_not() -> None:
    with_name = compose(
        MailTemplate.invite, Lang.ru, to="a@b.org", server_url=SAMPLE_SERVER,
        link=f"{SAMPLE_SERVER}/invite/t", values={"inviter": "Анна"},
    )  # fmt: skip
    without = compose(
        MailTemplate.invite, Lang.ru, to="a@b.org", server_url=SAMPLE_SERVER,
        link=f"{SAMPLE_SERVER}/invite/t", values={"inviter": None},
    )  # fmt: skip

    assert "Анна приглашает вас в Студию" in with_name.text
    assert "Пригласил: Анна" in with_name.text
    assert "Вас пригласили в Студию" in without.text
    assert "Пригласил" not in without.text


@pytest.mark.parametrize("lang", list(Lang))
def test__passkey_notices__carry_name_count_and_a_link_to_account_settings(lang: Lang) -> None:
    added = sample_mail(MailTemplate.passkey_added, lang)
    reset = sample_mail(MailTemplate.passkey_reset, lang)

    assert "MacBook, Touch ID" in added.text
    assert f"{SAMPLE_SERVER}/settings/account" in added.text
    assert f'href="{SAMPLE_SERVER}/settings/account"' in reset.html
    assert re.search(r": 2\n", reset.text)


@pytest.mark.parametrize("lang", list(Lang))
def test__notification_mails__link_to_the_inbox(lang: Lang) -> None:
    for template in (MailTemplate.project_invitation, MailTemplate.access_request, MailTemplate.transfer_request):
        mail = sample_mail(template, lang)
        assert f"{SAMPLE_SERVER}/inbox" in mail.text
        assert "Anna Petrova" in mail.subject or "Анна Петрова" in mail.subject


def test__project_invitation_link__shows_message_role_and_expiry_date() -> None:
    mail = sample_mail(MailTemplate.project_invitation_link, Lang.ru)

    assert "Редактор" in mail.text
    assert "> Добавил вас в проект" in mail.text
    assert "до 10.11.2026 14:30 UTC" in mail.text
    assert "10.11.2026 14:30 UTC" in mail.html
    en = sample_mail(MailTemplate.project_invitation_link, Lang.en)
    assert "until 2026-11-10 14:30 UTC" in en.text
    assert "as Editor" in en.text


def test__code_block__is_large_monospace_with_expiry_hint() -> None:
    mail = compose(
        MailTemplate.verify_email,
        Lang.ru,
        to="a@b.org",
        server_url=SAMPLE_SERVER,
        code="482 913",
        ttl=timedelta(minutes=10),
    )

    assert "482 913" in mail.text
    assert "Код действует 10 минут." in mail.text
    assert "monospace" in mail.html
    assert "font:700 32px" in mail.html


@pytest.mark.parametrize("lang", list(Lang))
def test__values_from_users__are_escaped_in_html_and_never_break_the_subject(lang: Lang) -> None:
    mail = compose(
        MailTemplate.project_invitation_link,
        lang,
        to="a@b.org",
        server_url=SAMPLE_SERVER,
        link=f"{SAMPLE_SERVER}/invitation/t",
        values={"actor": _EVIL, "project": _EVIL, "role": "editor"},
        note=_EVIL,
    )
    header = compose(
        MailTemplate.project_invitation, lang, to="a@b.org", server_url=SAMPLE_SERVER,
        values={"actor": "A", "project": "P\r\nBcc: evil@example.org", "role": "editor"},
    )  # fmt: skip

    assert "<script" not in mail.html
    assert "&lt;script&gt;" in mail.html
    assert "&quot;q&quot;" in mail.html
    assert "{not_a_placeholder}" in mail.html
    assert "\r" not in mail.subject
    assert "\n" not in mail.subject
    assert len(mail.subject) <= 150
    assert "\r" not in header.subject
    assert "\n" not in header.subject
    assert "P Bcc: evil@example.org" in header.subject  # остался текстом темы, но не отдельным заголовком


def test__subject_drops_control_and_bidi_characters_and_is_capped() -> None:
    mail = compose(
        MailTemplate.project_invitation, Lang.en, to="a@b.org", server_url=SAMPLE_SERVER,
        values={"actor": "A‮B\x00C\n", "project": "P" * 500, "role": "reader"},
    )  # fmt: skip

    assert "‮" not in mail.subject
    assert "\x00" not in mail.subject
    assert len(mail.subject) <= 150
    assert mail.subject.endswith("…")


def test__multiline_note__keeps_line_breaks_in_both_parts() -> None:
    mail = compose(
        MailTemplate.project_invitation_link, Lang.en, to="a@b.org", server_url=SAMPLE_SERVER,
        link=f"{SAMPLE_SERVER}/invitation/t", values={"actor": "A", "project": "P", "role": "reader"},
        note="first\nsecond\n\n\n\nthird",
    )  # fmt: skip

    assert "> first\n> second\n>\n> third" in mail.text
    assert "first<br>second<br><br>third" in mail.html


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "https://evil.example.org/verify/t",
        "https://studio.example.org.evil.org/x",
        "/verify/t",
        "",
        None,
    ],
)
def test__links__only_to_the_public_address_of_the_installation(link: str | None) -> None:
    mail = compose(MailTemplate.verify_email, Lang.en, to="a@b.org", server_url=SAMPLE_SERVER, link=link)

    parsed = _parsed(mail.html)
    assert all(href == SAMPLE_SERVER or href.startswith(SAMPLE_SERVER + "/") for href in parsed.hrefs)
    assert "evil" not in mail.html or "evil" in (link or "")
    assert not any("javascript" in href for href in parsed.hrefs)
    assert "Confirm address" not in mail.html


def test__link_with_whitespace_or_control_characters__is_not_clickable() -> None:
    for link in (f"{SAMPLE_SERVER}/verify/t\nBcc: x", f"{SAMPLE_SERVER}/verify/t x", f"{SAMPLE_SERVER}/a‮b"):
        mail = compose(MailTemplate.verify_email, Lang.en, to="a@b.org", server_url=SAMPLE_SERVER, link=link)
        assert "Confirm address" not in mail.html


def test__without_public_url__the_link_stays_in_text_but_has_no_button() -> None:
    mail = compose(
        MailTemplate.reset_password, Lang.ru, to="a@b.org", server_url=None, link="/reset/tok", ttl=timedelta(hours=1)
    )

    assert "/reset/tok" in mail.text
    assert "/reset/tok" in mail.html
    assert "href=" not in mail.html
    assert "Задать новый пароль" not in mail.html
    assert "Сервер:" not in mail.text


@pytest.mark.parametrize("bad", ["ftp://studio.example.org", "studio.example.org", "https://", "https://a b.org"])
def test__invalid_public_url__is_treated_as_unset(bad: str) -> None:
    mail = compose(MailTemplate.reset_notice, Lang.en, to="a@b.org", server_url=bad)

    assert "href=" not in mail.html


def test__server_url_with_path_and_trailing_slash__is_kept_without_the_slash() -> None:
    mail = compose(
        MailTemplate.passkey_added,
        Lang.en,
        to="a@b.org",
        server_url="https://corp.example.org/studio/",
        values={"name": "K"},
    )

    assert "https://corp.example.org/studio/settings/account" in mail.text
    assert "corp.example.org/studio" in mail.html


def test__missing_actor_and_project__fall_back_to_neutral_words() -> None:
    mail = compose(MailTemplate.access_request, Lang.en, to="a@b.org", server_url=SAMPLE_SERVER, values={})

    assert "A Studio user requests access to the project “an untitled project”" in mail.text


def test__resolve_lang__account_locale_first_then_interface_language_then_russian() -> None:
    set_interface_language(None)
    assert resolve_lang("en") is Lang.en
    assert resolve_lang("ru") is Lang.ru
    assert resolve_lang(None) is Lang.ru
    assert resolve_lang("de") is Lang.ru
    set_interface_language("en")
    try:
        assert resolve_lang(None) is Lang.en
        assert resolve_lang("") is Lang.en
        assert resolve_lang("ru") is Lang.ru
    finally:
        set_interface_language(None)


@pytest.mark.parametrize(
    ("seconds", "ru", "en"),
    [
        (3600, "1 час", "1 hour"),
        (2 * 3600, "2 часа", "2 hours"),
        (5 * 3600, "5 часов", "5 hours"),
        (21 * 3600, "21 час", "21 hours"),
        (11 * 3600, "11 часов", "11 hours"),
        (24 * 3600, "1 день", "1 day"),
        (7 * 86400, "7 дней", "7 days"),
        (2 * 86400, "2 дня", "2 days"),
        (600, "10 минут", "10 minutes"),
        (60, "1 минуту", "1 minute"),
        (90 * 60, "90 минут", "90 minutes"),
        (30, "1 минуту", "1 minute"),
    ],
)
def test__duration__uses_the_right_plural_form(seconds: int, ru: str, en: str) -> None:
    assert format_duration(Lang.ru, seconds) == ru
    assert format_duration(Lang.en, seconds) == en
