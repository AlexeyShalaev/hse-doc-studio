"""Письма сервера: единый шаблон, тексты ru и en, HTML и текстовая часть (multipart/alternative)."""

from hse_doc_studio.core.mail.compose import MailTemplate, RenderedMail, compose, resolve_lang

__all__ = ["MailTemplate", "RenderedMail", "compose", "resolve_lang"]
