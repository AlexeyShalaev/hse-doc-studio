from __future__ import annotations

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError

_MAX_REF_LENGTH = 200
_FORBIDDEN_CHARS = frozenset(" ~^:?*[\\\x7f")
_FORBIDDEN_NAMES = frozenset({"@", "HEAD"})


def validate_ref_name(name: str) -> str:
    """Имя ветки или тега по правилам `git check-ref-format`, плюс запрет ведущего «-».

    Имя уходит в argv git как есть, поэтому «-x» стало бы опцией. Возвращает имя
    без изменений или поднимает `VcsInvalidRefError`.
    """
    reason = _ref_problem(name)
    if reason is not None:
        raise VcsInvalidRefError(name, reason)
    return name


def validate_revision(rev: str) -> str:
    """Идентификатор коммита или ревизия из запроса: непустой, без ведущего «-», без управляющих символов."""
    if not rev or rev.startswith("-") or any(ord(ch) < 0x20 or ch == "\x7f" for ch in rev):  # noqa: PLR2004
        raise VcsInvalidRefError(rev, localized_error("недопустимая ревизия", "invalid revision"))
    return rev


def _ref_problem(name: str) -> str | None:  # noqa: C901, PLR0911
    if not name or not name.strip():
        return localized_error("имя не может быть пустым", "the name cannot be empty")
    if len(name) > _MAX_REF_LENGTH:
        return localized_error("имя слишком длинное", "the name is too long")
    if name.startswith("-"):
        return localized_error("имя не может начинаться с «-»", "the name cannot start with '-'")
    if name in _FORBIDDEN_NAMES:
        return localized_error("зарезервированное имя", "reserved name")
    if any(ord(ch) < 0x20 or ch in _FORBIDDEN_CHARS for ch in name):  # noqa: PLR2004
        return localized_error(
            "имя содержит недопустимые символы (пробел, управляющие, ~ ^ : ? * [ \\)",
            "the name contains forbidden characters (space, control, ~ ^ : ? * [ \\)",
        )
    if ".." in name or "@{" in name or name.endswith("."):
        return localized_error("недопустимая последовательность в имени", "forbidden sequence in the name")
    if name.startswith("/") or name.endswith("/") or "//" in name:
        return localized_error("недопустимые разделители «/» в имени", "misplaced '/' in the name")
    for part in name.split("/"):
        if part.startswith(".") or part.endswith(".lock"):
            return localized_error(
                "компонент имени не может начинаться с «.» или заканчиваться на «.lock»",
                "a name component cannot start with '.' or end with '.lock'",
            )
    return None
