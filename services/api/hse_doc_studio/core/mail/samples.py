"""Образцы писем с выдуманными данными: предпросмотр в админке, выгрузка в файлы и тесты."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail.compose import MailTemplate, RenderedMail, compose, format_moment

SAMPLE_RECIPIENT = "anna.petrova@example.org"
SAMPLE_SERVER = "https://studio.example.org"

_PEOPLE = {Lang.ru: ("Анна Петрова", "Курсовая работа по ГОСТ"), Lang.en: ("Anna Petrova", "Coursework draft")}
_NOTES = {
    Lang.ru: "Добавляю вас в проект, посмотрите, пожалуйста, введение до пятницы.",
    Lang.en: "Added you to the project, please take a look at the introduction by Friday.",
}
_PROFILES = {
    Lang.ru: "Заявка на тему КП (SmartLMS)",
    Lang.en: "Course project topic application (SmartLMS)",
}
_COMMENTS = {
    Lang.ru: "Уточните цель проекта во введении, после этого подпишу.",
    Lang.en: "Please clarify the project goal in the introduction, then I will sign.",
}
_CHANGES = {
    Lang.ru: "Исправил формулировку темы по замечанию руководителя.",
    Lang.en: "Rephrased the topic after the supervisor's comment.",
}
_CHANGED = {Lang.ru: "«Заявление о выборе темы»", Lang.en: "«Topic application»"}
_EXPIRES = datetime(2026, 11, 10, 14, 30, tzinfo=UTC)
_DEADLINE = datetime(2026, 11, 15, 20, 59, tzinfo=UTC)
_TOKEN = "sampletoken0000"  # noqa: S105 — образец, не секрет
# Страница подписи и точка сдачи: адреса без токена, как в настоящих письмах маршрута.
_SIGN_PATH = "/sign/5b0c1d2e-3f40-4152-8364-758697a8b9c0/0d1e2f30-4152-4637-8899-aabbccddeeff"
_CHECKPOINT_PATH = "/projects/5b0c1d2e-3f40-4152-8364-758697a8b9c0/submit/cp/topic-approval"


@dataclass(frozen=True)
class _Sample:
    path: str | None = None
    ttl: timedelta | None = None
    expires_at: datetime | None = None
    values: tuple[str, ...] = ()
    note: Mapping[Lang, str] | None = None
    # Ссылка с токеном (`<path>/<token>`) или готовый адрес страницы.
    token: bool = True


_PROJECT = ("actor", "project", "role")
_SIGNING = ("actor", "project", "profile", "deadline")

_SAMPLES: dict[MailTemplate, _Sample] = {
    MailTemplate.verify_email: _Sample("/verify", ttl=timedelta(hours=48)),
    MailTemplate.reset_password: _Sample("/reset", ttl=timedelta(hours=1)),
    MailTemplate.invite: _Sample("/invite", ttl=timedelta(days=7), values=("inviter",)),
    MailTemplate.email_change: _Sample("/confirm-email", ttl=timedelta(hours=48)),
    MailTemplate.reset_notice: _Sample(),
    MailTemplate.passkey_added: _Sample(values=("name",)),
    MailTemplate.passkey_reset: _Sample(values=("count",)),
    MailTemplate.project_invitation: _Sample(values=_PROJECT),
    MailTemplate.project_invitation_link: _Sample("/invitation", expires_at=_EXPIRES, values=_PROJECT, note=_NOTES),
    MailTemplate.access_request: _Sample(values=_PROJECT),
    MailTemplate.transfer_request: _Sample(values=_PROJECT),
    MailTemplate.signing_request: _Sample(_SIGN_PATH, values=_SIGNING, token=False),
    MailTemplate.signing_request_sign: _Sample(_SIGN_PATH, values=_SIGNING, token=False),
    MailTemplate.signing_request_new_version: _Sample(
        _SIGN_PATH, values=(*_SIGNING, "changed"), note=_CHANGES, token=False
    ),
    MailTemplate.signing_reminder: _Sample(_SIGN_PATH, values=_SIGNING, token=False),
    MailTemplate.signing_skipped: _Sample(_SIGN_PATH, values=("actor", "project", "profile"), token=False),
    MailTemplate.signing_returned: _Sample(_CHECKPOINT_PATH, values=("actor", "project"), note=_COMMENTS, token=False),
    MailTemplate.signing_completed: _Sample(_CHECKPOINT_PATH, values=("project", "profile"), token=False),
    MailTemplate.checkpoint_due: _Sample(_CHECKPOINT_PATH, values=("project", "profile", "deadline"), token=False),
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
        "profile": _PROFILES[lang],
        "deadline": format_moment(lang, _DEADLINE),
        "changed": _CHANGED[lang],
    }
    suffix = f"/{_TOKEN}" if sample.token else ""
    link = f"{(server_url or '').rstrip('/')}{sample.path}{suffix}" if sample.path else None
    return compose(
        template,
        lang,
        to=SAMPLE_RECIPIENT,
        server_url=server_url,
        link=link,
        ttl=sample.ttl,
        expires_at=sample.expires_at,
        values={key: available[key] for key in sample.values},
        note=sample.note[lang] if sample.note else None,
    )
