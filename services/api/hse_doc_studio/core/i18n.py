"""Interface (UI) language resolution for the backend.

The interface language is the language of the agent CONVERSATION and any backend
prose meant for the user. It is INDEPENDENT from a project's document language
(`project.lang` / the `set_language` chat tool): a Russian thesis can be edited
under an English interface, and the agent then replies in English while talking
ABOUT the Russian document.

Resolution order (see `current_interface_language`):
  1. the per-request `X-Interface-Language` header (set into the context var by
     the FastAPI middleware; inherited by background tasks spawned during the
     request, e.g. an agent run);
  2. an explicit fallback the caller passes (typically the persisted
     `settings.interface_language`, kept current by the frontend);
  3. Russian.
"""

from __future__ import annotations

import contextvars

from hse_doc_studio.core.enums import Lang

_VALID = ("ru", "en")

# default=None means "not set for this context" so callers can distinguish an
# absent header from an explicit choice and fall back to stored settings.
_interface_language: contextvars.ContextVar[str | None] = contextvars.ContextVar("interface_language", default=None)


def coerce_lang(value: object) -> Lang:
    """Map an arbitrary value to a supported interface language (default ru)."""
    return Lang.en if value == "en" else Lang.ru


def set_interface_language(value: object) -> None:
    """Store the request/task interface language (invalid → cleared to None)."""
    _interface_language.set(value if value in _VALID else None)


def peek_interface_language() -> str | None:
    """Raw context-var value: "ru"/"en" if set, else None. Use to decide whether
    to fill it from settings before spawning a background task."""
    return _interface_language.get()


def current_interface_language(fallback: object = "ru") -> Lang:
    """Resolve the interface language: context var (header) → fallback → ru."""
    raw = _interface_language.get()
    return coerce_lang(raw if raw in _VALID else fallback)


def localized_error(ru: str, en: str) -> str:
    """Pick a user-facing message by the current interface language.

    The standard shape for a `raise ValueError(...)`/similar message that may
    reach the frontend as `detail` — same resolution as `current_interface_language`,
    just inlined at the raise site instead of a manual ternary each time.
    """
    return en if current_interface_language() is Lang.en else ru
