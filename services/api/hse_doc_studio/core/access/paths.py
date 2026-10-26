"""Пути в проекте с точки зрения доступа: нормализация, вывод или исходник, область автора."""

from __future__ import annotations

from typing import Literal

from hse_doc_studio.core.access.entities import Grant, ProjectAcl, Role
from hse_doc_studio.core.team import RESERVED_SLUGS, SHARED_DIR, split_instance_id

PathClass = Literal["output", "source"]

_BUILD_DIR = ".build"
# Под `.build/` выводом считаются только PDF и лог сборки. Остальное (synctex, aux, fls, bbl)
# хранит имена исходников, номера строк и тексты разделов, то есть это исходник.
_BUILD_OUTPUT_SUFFIXES = (".pdf", ".log")


def normalize_path(path: str) -> str | None:
    """POSIX-путь внутри проекта без `.`/пустых сегментов; None, если путь недопустим.

    Недопустимы: `..`, обратный слэш, ведущий слэш, NUL и пустой результат.
    """
    if not path or "\\" in path or "\0" in path or path.startswith("/"):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def classify_path(path: str | None) -> PathClass:
    """`output` для PDF и лога сборки под `.build/`, иначе `source`.

    Нет пути или путь недопустим: `source`, то есть строже.
    """
    normalized = normalize_path(path) if path else None
    if normalized is None:
        return "source"
    parts = normalized.split("/")
    name = parts[-1].lower()
    if name.endswith(".pdf") or (_BUILD_DIR in parts[:-1] and name.endswith(_BUILD_OUTPUT_SUFFIXES)):
        return "output"
    return "source"


def scope_path_of_instance_id(instance_id: str) -> str | None:
    """Область записи для id экземпляра `<база>--<автор>` (документ, форма, слот): слаг автора.

    Слаг стоит первым сегментом, как у файлов автора, так что дальше работает обычная проверка
    области. Id без автора в область автора не входит: None, пишет только владелец и `can_edit_all`.
    """
    return split_instance_id(instance_id)[1]


def path_in_author_scope(acl: ProjectAcl, grant: Grant, path: str | None) -> bool:
    """Можно ли писать в `path`: в solo-проекте всегда, в team-проекте только в свою папку и shared/.

    Владелец и право `can_edit_all` пишут везде. Недопустимый путь (`..` и подобное)
    не проходит никто. Без пути в team-проекте право только у владельца и `can_edit_all`.
    """
    normalized = None
    if path is not None:
        normalized = normalize_path(path)
        if normalized is None:
            return False
    if not acl.team or grant.role is Role.owner or grant.can_edit_all:
        return True
    if normalized is None:
        return False
    base = normalized.split("/", 1)[0]
    if base == SHARED_DIR:
        return acl.shared_enabled
    return grant.persona_slug is not None and base == grant.persona_slug and base not in RESERVED_SLUGS
