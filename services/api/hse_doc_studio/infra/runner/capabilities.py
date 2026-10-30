"""Теги раннера по окружению: задачу с тегом, которого у раннера нет, он не получит."""

from __future__ import annotations

from collections.abc import Callable

from hse_doc_studio.core.jobs.entities import pack_job_tags
from hse_doc_studio.core.jobs.pack import ArchiveFormat
from hse_doc_studio.core.jobs.relay import RELAY_TAG
from hse_doc_studio.infra.submission.pack_executor import is_archive_format_available


def detect_tags(
    *,
    office_url: str | None,
    tex_available: bool = False,
    archive_available: Callable[[str], bool] = is_archive_format_available,
    ai_relay: bool = False,
) -> frozenset[str]:
    """`verify` и `pack` есть всегда (zip и tar.gz нативные), остальное по окружению: docker даёт `tex`,
    объявленные ИИ-адреса дают `ai`."""
    tags = {"verify", *pack_job_tags(ArchiveFormat.zip)}
    if ai_relay:
        tags.add(RELAY_TAG)
    if office_url:
        tags.add("office")
    if tex_available:
        tags.add("tex")
    for fmt in (ArchiveFormat.sevenz, ArchiveFormat.rar):
        if archive_available(fmt.value):
            tags.update(pack_job_tags(fmt))
    return frozenset(tags)
