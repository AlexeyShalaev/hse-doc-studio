"""Предел на размер файлов чужой ветки, которые Студия читает в память и пишет в проект."""

from __future__ import annotations

from collections.abc import Iterable

from hse_doc_studio.core.git_sync.entities import TreeEntry
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.i18n import localized_error

_MEGABYTE = 1_000_000
_MAX_LISTED = 5


def ensure_incoming_fits(entries: Iterable[TreeEntry], policy: GitSyncPolicy) -> None:
    """Отказ до чтения содержимого, если файл или все файлы вместе больше предела.

    Размеры берутся из дерева (`ls-tree -l`), содержимое не читается: гигабайтный блоб из нулей весит в пакете
    несколько мегабайт, поэтому ни размер пакета, ни время выборки его не останавливают.
    """
    total = 0
    large: list[TreeEntry] = []
    for entry in entries:
        size = entry.size or 0
        total += size
        if size > policy.max_incoming_blob_bytes:
            large.append(entry)
    if large:
        shown = ", ".join(entry.path for entry in large[:_MAX_LISTED])
        limit = policy.max_incoming_blob_bytes // _MEGABYTE
        raise git_error(
            GitErrorCode.git_error,
            tail=localized_error(
                f"В чужой ветке есть файл больше {limit} МБ, Студия его не принимает: {shown}",
                f"The remote branch has a file larger than {limit} MB, which the Studio does not accept: {shown}",
            ),
            paths=[entry.path for entry in large[:_MAX_LISTED]],
        )
    if total > policy.max_incoming_total_bytes:
        limit = policy.max_incoming_total_bytes // _MEGABYTE
        raise git_error(
            GitErrorCode.git_error,
            tail=localized_error(
                f"Файлы чужой ветки вместе больше {limit} МБ, Студия их не принимает",
                f"The files of the remote branch together exceed {limit} MB, which the Studio does not accept",
            ),
        )
