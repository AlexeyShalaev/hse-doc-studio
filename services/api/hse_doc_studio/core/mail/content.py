"""Содержимое письма до вёрстки: одно описание, из которого строятся и текстовая часть, и HTML."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail.catalog import fill_html, fill_text


@dataclass(frozen=True)
class Text:
    """Строка словаря со значениями: в текст они идут как есть, в HTML экранируются и выделяются."""

    template: str
    values: Mapping[str, str] = field(default_factory=dict)

    def plain(self) -> str:
        return fill_text(self.template, self.values)

    def html(self, strong: str) -> str:
        return fill_html(self.template, self.values, strong=strong)


@dataclass(frozen=True)
class Row:
    label: str
    value: str


@dataclass(frozen=True)
class Action:
    label: str
    href: str


@dataclass(frozen=True)
class Block:
    title: str
    body: str


@dataclass(frozen=True)
class MailContent:
    lang: Lang
    brand: str
    tagline: str
    subject: str
    preheader: Text
    title: Text
    lead: Text
    rows: tuple[Row, ...] = ()
    action: Action | None = None
    # Ссылка без кнопки: адрес установки не задан, и ссылка относительная.
    plain_link: str | None = None
    code: str | None = None
    expiry: str | None = None
    note: Block | None = None
    context_title: str = ""
    context: tuple[Text, ...] = ()
    security_title: str = ""
    security: tuple[Text, ...] = ()
    fallback_label: str = ""
    footer_server_label: str = ""
    footer_recipient: str = ""
    footer_auto: str = ""
    server_url: str | None = None
    server_display: str = ""
