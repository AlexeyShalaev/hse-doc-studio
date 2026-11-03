"""Образцы писем с выдуманными данными: предпросмотр в админке, выгрузка в файлы и тесты."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail.compose import MailTemplate, RenderedMail, compose

SAMPLE_RECIPIENT = "anna.petrova@example.org"
SAMPLE_SERVER = "https://studio.example.org"

_PEOPLE = {Lang.ru: ("Анна Петрова", "Курсовая работа по ГОСТ"), Lang.en: ("Anna Petrova", "Coursework draft")}
_NOTES = {
    Lang.ru: "Добавил вас в проект, посмотрите, пожалуйста, введение до пятницы.",
    Lang.en: "Added you to the project, please take a look at the introduction by Friday.",
}
_EXPIRES = datetime(2026, 11, 10, 14, 30, tzinfo=UTC)
_TOKEN = "sampletoken0000"  # noqa: S105 — образец, не секрет


@dataclass(frozen=True)
class _Sample:
    path: str | None = None
    ttl: timedelta | None = None
    expires_at: datetime | None = None
    values: tuple[str, ...] = ()
    note: bool = False


_PROJECT = ("actor", "project", "role")

_SAMPLES: dict[MailTemplate, _Sample] = {
    MailTemplate.verify_email: _Sample("/verify", ttl=timedelta(hours=48)),
    MailTemplate.reset_password: _Sample("/reset", ttl=timedelta(hours=1)),
    MailTemplate.invite: _Sample("/invite", ttl=timedelta(days=7), values=("inviter",)),
    MailTemplate.email_change: _Sample("/confirm-email", ttl=timedelta(hours=48)),
    MailTemplate.reset_notice: _Sample(),
    MailTemplate.passkey_added: _Sample(values=("name",)),
    MailTemplate.passkey_reset: _Sample(values=("count",)),
    MailTemplate.project_invitation: _Sample(values=_PROJECT),
    MailTemplate.project_invitation_link: _Sample("/invitation", expires_at=_EXPIRES, values=_PROJECT, note=True),
    MailTemplate.access_request: _Sample(values=_PROJECT),
    MailTemplate.transfer_request: _Sample(values=_PROJECT),
    MailTemplate.smtp_test: _Sample(),
}


def sample_mail(template: MailTemplate, lang: Lang, *, server_url: str | None = SAMPLE_SERVER) -> RenderedMail:
    """Письмо `template` на языке `lang` с образцами данных; ссылки ведут на `server_url`."""
    sample = _SAMPLES[template]
    person, project = _PEOPLE[lang]
    available = {
        "actor": person,
        "inviter": person,
        "project": project,
        "role": "editor",
        "name": "MacBook, Touch ID",
        "count": 2,
    }
    link = f"{(server_url or '').rstrip('/')}{sample.path}/{_TOKEN}" if sample.path else None
    return compose(
        template,
        lang,
        to=SAMPLE_RECIPIENT,
        server_url=server_url,
        link=link,
        ttl=sample.ttl,
        expires_at=sample.expires_at,
        values={key: available[key] for key in sample.values},
        note=_NOTES[lang] if sample.note else None,
    )
