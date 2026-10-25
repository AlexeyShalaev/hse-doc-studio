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


class ProjectReadOnlyError(Exception):
    """Write refused: the project is read-only in this Studio.

    Its data was saved by a newer Studio (`write_compat` above ours), its
    template version is missing here, or a template update is in progress
    (see core.project_access). Routers map it to HTTP 423 Locked.
    """
