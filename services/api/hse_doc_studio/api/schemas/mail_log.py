"""Схемы журнала писем в админке (docs/design/mail-log.md, 6.2): список, карточка с превью, сводка за сутки.

Эталоны лежат в `contracts/server/pending/AdminMailLog*` до появления zod-схем фронтенда, затем переезжают в
`contracts/server/fixtures` (раздел 6.2 дизайна).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from hse_doc_studio.api.schemas.common import StrictModel

MailStatusName = Literal["sent", "failed", "not_sent", "suppressed"]
MailCauseName = Literal["user", "anonymous", "system"]
MailLangName = Literal["ru", "en"]


class AdminPersonRef(StrictModel):
    """Человек установки: получатель письма или тот, кто его вызвал."""

    id: str
    name: str
    email: str | None


class AdminMailLogFailure(StrictModel):
    """Ответ SMTP у `failed`: код, если сервер его дал, и очищенный текст (без логина и пароля SMTP)."""

    smtp_code: int | None
    text: str | None


class AdminMailLogProject(StrictModel):
    id: UUID
    # null, если проекта уже нет: строка журнала переживает удаление проекта.
    name: str | None


class AdminMailLogRef(StrictModel):
    """Объект письма: `signing_route`, `project_invitation`, `registration_invite`, `access_request`, `transfer`,
    `passkey`."""

    kind: str
    id: str


class AdminMailLogEntry(StrictModel):
    id: int
    at: datetime
    # Значение MailTemplate; вид, удалённый из этой версии, приходит как есть с `template_known: false`.
    template: str
    template_known: bool
    lang: MailLangName
    to_email: str
    # null, если адрес не принадлежит человеку установки или человек удалён.
    to_user: AdminPersonRef | None
    # Тема как ушла.
    subject: str
    status: MailStatusName
    # `smtp_off`, `email_unverified`, `account_blocked` или класс сбоя у `failed`.
    reason: str | None
    failure: AdminMailLogFailure | None
    message_id: str | None
    attempts: int
    duration_ms: int
    cause: MailCauseName
    actor: AdminPersonRef | None
    # Имя фоновой задачи у `cause: system`.
    task: str | None
    # Код сценария (`register`, `forgot_password`, `signing_auto_reminder` и т. д.).
    origin: str
    project: AdminMailLogProject | None
    ref: AdminMailLogRef | None


class AdminMailLogPage(StrictModel):
    """Страница по ключу, новые сверху: `next_cursor` непрозрачный, пустой на последней странице.

    `total_estimate` оценка числа строк без фильтров; с фильтрами null.
    """

    items: list[AdminMailLogEntry]
    next_cursor: str | None
    total_estimate: int | None


class AdminMailLogPreview(StrictModel):
    """Письмо, перерисованное без ссылок и сообщений людей; `subject` из перерисовки, в шапке `entry.subject`."""

    subject: str
    html: str
    text: str


class AdminMailLogDetail(StrictModel):
    entry: AdminMailLogEntry
    # null, если вида письма в этой версии больше нет.
    preview: AdminMailLogPreview | None
    link_hidden: bool
    note_hidden: bool
    rerendered: bool


class AdminMailLogLastFailure(StrictModel):
    at: datetime
    reason: str


class AdminMailLogSummary(StrictModel):
    """Полоса за сутки, счётчик меню и плашка «Почта не настроена»."""

    smtp_configured: bool
    window_hours: Literal[24]
    sent: int
    failed: int
    not_sent: int
    suppressed: int
    # Последний `failed` в окне сводки; null, если сбоев в окне не было.
    last_failure: AdminMailLogLastFailure | None
    retention_days: int
