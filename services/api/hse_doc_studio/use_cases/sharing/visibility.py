"""Что гость и ссылочное право видят в панели «Доступ»: только закреплённые строки, без участников."""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.repositories import ProjectAccessRow
from hse_doc_studio.core.listing import Found


def visible_rows_for(actor: Actor | None, rows: Found[ProjectAccessRow]) -> Found[ProjectAccessRow]:
    """Гость и вошедший по ссылке (гард положил в актора `link_id`) видят владельца и организацию-владельца:
    состав команды по ссылке не раскрывается. Почта владельца тоже: ссылку могли переслать кому угодно, а имя
    владельца и так видно на странице ссылки. Участникам список отдаётся как есть."""
    if actor is None or not (actor.is_guest or actor.link_id is not None):
        return rows
    pinned = [replace(row, detail=None) if row.subject_kind == "user" else row for row in rows.items if row.locked]
    return Found(pinned, len(pinned))
