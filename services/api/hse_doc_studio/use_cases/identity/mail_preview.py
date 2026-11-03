"""Предпросмотр писем для админа: каждое письмо на ru и en с образцами данных, ничего не отправляется."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.compose import server_origin
from hse_doc_studio.core.mail.samples import SAMPLE_SERVER, sample_mail
from hse_doc_studio.use_cases.admin.users import require_admin


@dataclass(frozen=True)
class MailPreview:
    template: MailTemplate
    lang: Lang
    subject: str
    text: str
    html: str
    templates: tuple[MailTemplate, ...]


class PreviewMailUC:
    def __init__(self, public_url: str | None = None) -> None:
        self._server_url = server_origin(public_url) or SAMPLE_SERVER

    def execute(self, actor: Actor, template: str | None, lang: str) -> MailPreview:
        require_admin(actor)
        try:
            kind = MailTemplate(template) if template else next(iter(MailTemplate))
            language = Lang(lang)
        except ValueError:
            raise IdentityError(
                IdentityErrorCode.input_invalid,
                localized_error("Неизвестный вид письма или язык.", "Unknown mail template or language."),
            ) from None
        mail = sample_mail(kind, language, server_url=self._server_url)
        return MailPreview(kind, language, mail.subject, mail.text, mail.html, tuple(MailTemplate))
