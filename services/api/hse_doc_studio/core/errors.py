from __future__ import annotations


class NotFoundError(Exception):
    """A requested entity (project/document/signature slot/chat session/...)
    doesn't exist.

    Routers map this to HTTP 404 by TYPE, never by sniffing the message text
    for a substring like "not found" — that pattern silently breaks once a
    message is localized to a language that doesn't contain the English
    phrase. Use cases raise this instead of a bare `ValueError` whenever the
    failure is genuinely "doesn't exist"; a `ValueError` (or a more specific
    domain exception) stays for actual bad-input/validation failures, which
    routers keep mapping to 400.
    """
