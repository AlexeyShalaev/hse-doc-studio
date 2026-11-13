"""Пометка `signing_note` в ответе тулов MCP, которые правят и собирают (docs/design/signing-route.md, 12.10).

Маршрут подписывает версию, снятую при отправке: правка и пересборка документа на подписании маршрут не трогают, но
и в подписываемую версию не попадают. Модель узнаёт об этом из пометки в ответе тула, это не отказ: правка уже
сделана. Новую версию отправляет человек в интерфейсе («Отправить новую версию»), MCP её не отправляет.

Какой документ задет, считается как у мягкого предупреждения интерфейса (12.7): файл в папке исходника документа
задевает только его, общий файл (`common/`, библиография, корень проекта), поля проекта, обновление шаблона и
история задевают все документы на подписании. Локально маршрутов нет, и пометки нет.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.agent.entities import ToolResult
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.dates import format_numeric, to_display
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate, SigningDoc
from hse_doc_studio.use_cases.documents.list_documents import ListDocumentsInput, ListDocumentsUC

NOTE_KEY = "signing_note"


@dataclass(frozen=True)
class EditTarget:
    """Что меняет вызов: файлы по путям, документы по id или проект целиком."""

    paths: tuple[str, ...] = ()
    doc_ids: tuple[str, ...] = ()
    project: bool = False


def _normalize(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def folder_of(source_file: str) -> str:
    """Папка исходника документа: `vkr/vkr.tex` даёт `vkr`, `ivanov/vkr/vkr.tex` даёт `ivanov/vkr`, файл в корне
    пустую строку (у такого документа своей папки нет)."""
    normalized = _normalize(source_file)
    cut = normalized.rfind("/")
    return "" if cut <= 0 else normalized[:cut]


def doc_of_path(path: str, folders: Mapping[str, str]) -> str | None:
    """Документ, в папке которого лежит файл (самая глубокая папка выигрывает); None у общего файла."""
    target = _normalize(path)
    best: tuple[str, str] | None = None
    for doc_id, folder in folders.items():
        if not folder or (target != folder and not target.startswith(f"{folder}/")):
            continue
        if best is None or len(folder) > len(best[1]):
            best = (doc_id, folder)
    return best[0] if best is not None else None


def affected(target: EditTarget, held: Sequence[SigningDoc], folders: Mapping[str, str]) -> tuple[SigningDoc, ...]:
    """Документы на подписании, которые задевает вызов, в порядке `held`."""
    if not held:
        return ()
    whole = target.project
    ids: set[str] = set(target.doc_ids)
    for path in target.paths:
        doc_id = doc_of_path(path, folders)
        if doc_id is None:
            whole = True
        else:
            ids.add(doc_id)
    return tuple(held) if whole else tuple(doc for doc in held if doc.doc_id in ids)


def _date(at: datetime | None) -> str | None:
    if at is None:
        return None
    return format_numeric(to_display(at).date())


_NEXT = (
    "Новую версию на подпись отправляет человек в интерфейсе («Отправить новую версию» в карточке «Подписание»)",
    "A person sends the new version for signing in the interface (“Send new version” on the “Signing” card)",
)


def note_text(docs: Sequence[SigningDoc]) -> str:
    """Текст пометки: какой документ на подписании и от какой даты версия, которую подписывают."""
    if len(docs) == 1:
        doc = docs[0]
        day = _date(doc.sent_at)
        ru_version = f"подписываемую версию от {day}" if day else "подписываемую версию"
        en_version = f"the version being signed, sent on {day}" if day else "the version being signed"
        return localized_error(
            f"Документ на подписании ({doc.doc_id}): изменения не попадут в {ru_version}. {_NEXT[0]}.",
            f"The document is out for signing ({doc.doc_id}): the changes will not reach {en_version}. {_NEXT[1]}.",
        )
    ru_items, en_items = [], []
    for doc in docs:
        day = _date(doc.sent_at)
        ru_items.append(f"{doc.doc_id} (версия от {day})" if day else doc.doc_id)
        en_items.append(f"{doc.doc_id} (version of {day})" if day else doc.doc_id)
    return localized_error(
        f"Документы на подписании: {', '.join(ru_items)}. Изменения не попадут в подписываемые версии. {_NEXT[0]}.",
        f"Documents out for signing: {', '.join(en_items)}. The changes will not reach the versions being signed. "
        f"{_NEXT[1]}.",
    )


def with_note(result: ToolResult, note: str) -> ToolResult:
    """Пометка в ответе тула: полем `signing_note` у ответа-объекта JSON, иначе строкой в конце текста."""
    try:
        body = json.loads(result.text)
    except ValueError:
        body = None
    if isinstance(body, dict):
        text = json.dumps({**body, NOTE_KEY: note}, ensure_ascii=False, indent=1)
    else:
        text = f"{result.text}\n\n{NOTE_KEY}: {note}" if result.text else f"{NOTE_KEY}: {note}"
    return replace(result, text=text)


class SigningNotes:
    """Пометка для вызова тула правки или сборки; None, если документов на подписании он не задевает."""

    def __init__(self, gate: ISigningRouteGate, documents: ListDocumentsUC) -> None:
        self._gate = gate
        self._documents = documents

    async def note(self, project_id: UUID, target: EditTarget) -> str | None:
        held = await self._gate.on_signing(project_id)
        if not held:
            return None
        folders = await self._folders(project_id) if target.paths else {}
        hit = affected(target, held, folders)
        return note_text(hit) if hit else None

    async def _folders(self, project_id: UUID) -> dict[str, str]:
        """Папки исходников документов проекта. Нужны все, а не только документов на подписании: файл в папке
        другого документа общим не считается."""
        out = await self._documents.execute(ListDocumentsInput(project_id=project_id))
        return {
            entry.document.id: folder_of(entry.source_file) for entry in out.entries if entry.source_file is not None
        }
