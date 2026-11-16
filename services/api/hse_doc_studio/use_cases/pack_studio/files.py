"""Файлы рабочего пространства: дерево, чтение и запись с ETag, точечные правки YAML, удаление.

- Версия файла это ETag содержимого (`core/file_version.py`, как у файлов проекта): запись с `If-Match` на устаревшую
  версию отвечает `stale_file` с текущим ETag и текстом, без заголовка пишет безусловно.
- Выпущенные версии и реестр выпусков защищены (`core/pack_studio/protection.py`) при любой записи и удалении.
- Правка YAML формой идёт только точечными правками по позициям узлов (D11, порт `IYamlEditor`,
  реализация в `infra/pack_studio/yaml_edits.py`):
  остальной текст, комментарии и выравнивание остаются байт в байт. Набор правок применяется целиком или никак.
- Внутри процесса запись одного пространства идёт под замком: проверка версии и запись не разрываются.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID
from weakref import WeakValueDictionary

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.file_version import etag_matches, file_etag
from hse_doc_studio.core.pack_studio.entities import PackTree, PackWorkspace
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.model import FileChange
from hse_doc_studio.core.pack_studio.paths import is_yaml, validate_rel_path
from hse_doc_studio.core.pack_studio.protocols import IPackWorkspaceFiles, IYamlEditor
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

MAX_YAML_OPS = 200


@dataclass(frozen=True)
class YamlOp:
    """Одна точечная правка: `set` (значение по пути), `insert` (элемент списка), `delete`, `move` (элемент списка)."""

    op: str
    path: tuple[str | int, ...]
    value: Any = None
    index: int | None = None
    to: int | None = None


@dataclass(frozen=True)
class PackFile:
    path: str
    content: bytes
    etag: str
    # Почему файл нельзя менять: `version_released` или `releases_read_only`; None: можно.
    read_only: str | None


@dataclass(frozen=True)
class WrittenFile:
    path: str
    etag: str
    size: int
    # Текст после точечных правок (у записи целиком не нужен: клиент его и прислал).
    content: str | None = None


@dataclass(frozen=True)
class TreeView:
    workspace: PackWorkspace
    tree: PackTree


class PackFilesService:
    def __init__(self, workspaces: PackWorkspaceService, files: IPackWorkspaceFiles, yaml_editor: IYamlEditor) -> None:
        self._workspaces = workspaces
        self._files = files
        self._yaml = yaml_editor
        self._locks: WeakValueDictionary[UUID, asyncio.Lock] = WeakValueDictionary()

    @property
    def max_file_bytes(self) -> int:
        return self._workspaces.limits.max_file_bytes

    async def tree(self, actor: Actor, workspace_id: UUID) -> TreeView:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        protection = await self._workspaces.protection(ws, root)
        limit = self._workspaces.limits.max_tree_files
        tree = await asyncio.to_thread(self._files.tree, root, protection, max_files=limit)
        return TreeView(workspace=ws, tree=tree)

    async def read(self, actor: Actor, workspace_id: UUID, raw_path: str) -> PackFile:
        path = validate_rel_path(raw_path)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        limit = self._workspaces.limits.max_read_bytes
        content = await asyncio.to_thread(self._files.read, root, path, max_bytes=limit)
        reason = (await self._workspaces.protection(ws, root)).read_only_reason(path)
        return PackFile(path, content, file_etag(content), reason.value if reason is not None else None)

    async def write(
        self, actor: Actor, workspace_id: UUID, raw_path: str, content: bytes, if_match: str | None
    ) -> WrittenFile:
        path = validate_rel_path(raw_path)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        self._check_size(len(content))
        async with self._lock(ws.id):
            (await self._workspaces.protection(ws, root)).check_write(path)
            await self._check_version(root, path, if_match)
            await asyncio.to_thread(self._files.write, root, path, content)
        return WrittenFile(path, file_etag(content), len(content))

    async def put(  # noqa: PLR0913 — путь, содержимое, условие записи и ошибки создания и правки
        self,
        actor: Actor,
        workspace_id: UUID,
        raw_path: str,
        content: bytes,
        if_match: str | None,
        *,
        taken: PackStudioError,
        missing: PackStudioError,
    ) -> WrittenFile:
        """Запись «создать или поправить» под замком пространства (сценарии, срез O6). Без `If-Match` файла быть не
        должно (`taken` иначе: запись не затирает чужой файл молча), с `If-Match` он должен быть (`missing` иначе) и
        совпасть по версии (`stale_file`)."""
        path = validate_rel_path(raw_path)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        self._check_size(len(content))
        async with self._lock(ws.id):
            (await self._workspaces.protection(ws, root)).check_write(path)
            current = await self._read_or_none(root, path)
            _check_put(current, if_match, taken, missing)
            if content != current:
                await asyncio.to_thread(self._files.write, root, path, content)
        return WrittenFile(path, file_etag(content), len(content))

    async def patch_yaml(
        self, actor: Actor, workspace_id: UUID, raw_path: str, ops: Sequence[YamlOp], if_match: str | None
    ) -> WrittenFile:
        return await self.edit_yaml(actor, workspace_id, raw_path, lambda text: _apply(self._yaml, text, ops), if_match)

    async def edit_yaml(
        self, actor: Actor, workspace_id: UUID, raw_path: str, edit: Callable[[str], str], if_match: str | None
    ) -> WrittenFile:
        """Правка текста YAML под замком пространства: проверка версии, защита выпущенных, запись, если текст другой.

        `edit` получает текущий текст и отдаёт новый (точечные правки, места подписей); его `PackStudioError` уходит
        как есть, файл не меняется.
        """
        path = validate_rel_path(raw_path)
        if not is_yaml(path):
            raise PackStudioError(PackStudioErrorCode.not_yaml)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        async with self._lock(ws.id):
            (await self._workspaces.protection(ws, root)).check_write(path)
            current = await self._check_version(root, path, if_match)
            if current is None:
                raise PackStudioError(PackStudioErrorCode.file_not_found, path=path)
            try:
                text = current.decode("utf-8")
            except UnicodeDecodeError:
                raise PackStudioError(PackStudioErrorCode.not_yaml) from None
            edited = edit(text)
            data = edited.encode("utf-8")
            self._check_size(len(data))
            if data != current:
                await asyncio.to_thread(self._files.write, root, path, data)
        return WrittenFile(path, file_etag(data), len(data), content=edited)

    async def apply_changes(
        self,
        actor: Actor,
        workspace_id: UUID,
        guard: str,
        if_match: str | None,
        plan: Callable[[Path], Sequence[FileChange]],
    ) -> tuple[FileChange, ...]:
        """Операция на несколько файлов под замком пространства (формы T11 и T12: поле, документ, перевод).

        `guard` это файл, на версию которого опирался клиент (`If-Match`), `plan` считает записи и удаления по папке
        паков (в потоке, его `PackStudioError` уходит как есть). Защита выпущенных версий проверяется до первой
        записи по всем путям; запись идёт по порядку плана.
        """
        guard_path = validate_rel_path(guard)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        async with self._lock(ws.id):
            protection = await self._workspaces.protection(ws, root)
            protection.check_write(guard_path)
            if await self._check_version(root, guard_path, if_match) is None:
                raise PackStudioError(PackStudioErrorCode.file_not_found, path=guard_path)
            changes = tuple(await asyncio.to_thread(plan, root))
            for change in changes:
                path = validate_rel_path(change.path)
                if change.content is None and await asyncio.to_thread(self._files.is_dir, root, path):
                    protection.check_delete_dir(path)
                else:
                    protection.check_write(path)
                if change.content is not None:
                    self._check_size(len(change.content))
            for change in changes:
                if change.content is None:
                    await asyncio.to_thread(self._files.delete, root, change.path)
                else:
                    await asyncio.to_thread(self._files.write, root, change.path, change.content)
        return changes

    async def delete(self, actor: Actor, workspace_id: UUID, raw_path: str, if_match: str | None) -> None:
        path = validate_rel_path(raw_path)
        ws, root = await self._workspaces.ready(actor, workspace_id)
        async with self._lock(ws.id):
            protection = await self._workspaces.protection(ws, root)
            if await asyncio.to_thread(self._files.is_dir, root, path):
                protection.check_delete_dir(path)
            else:
                protection.check_write(path)
                if await self._check_version(root, path, if_match) is None:
                    raise PackStudioError(PackStudioErrorCode.file_not_found, path=path)
            await asyncio.to_thread(self._files.delete, root, path)

    async def _read_or_none(self, root: Path, path: str) -> bytes | None:
        try:
            return await asyncio.to_thread(
                self._files.read, root, path, max_bytes=self._workspaces.limits.max_read_bytes
            )
        except PackStudioError as exc:
            if exc.code is not PackStudioErrorCode.file_not_found:
                raise
            return None

    async def _check_version(self, root: Path, path: str, if_match: str | None) -> bytes | None:
        """Текущее содержимое (None: файла нет); `stale_file`, если клиент опирался на другую версию."""
        limit = self._workspaces.limits.max_read_bytes
        try:
            current: bytes | None = await asyncio.to_thread(self._files.read, root, path, max_bytes=limit)
        except PackStudioError as exc:
            if exc.code is not PackStudioErrorCode.file_not_found:
                raise
            current = None
        if if_match is None:
            return current
        if current is None:
            # Клиент опирался на файл, которого уже нет (и `*` по HTTP требует существующий файл).
            raise PackStudioError(PackStudioErrorCode.stale_file, etag=None, content=None)
        if not etag_matches(if_match, current):
            raise PackStudioError(
                PackStudioErrorCode.stale_file,
                etag=file_etag(current),
                content=current.decode("utf-8", errors="replace"),
            )
        return current

    def _check_size(self, size: int) -> None:
        limit = self._workspaces.limits.max_file_bytes
        if size > limit:
            raise PackStudioError(PackStudioErrorCode.file_too_large, limit=limit)

    def _lock(self, workspace_id: UUID) -> asyncio.Lock:
        lock = self._locks.get(workspace_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[workspace_id] = lock
        return lock


def _check_put(current: bytes | None, if_match: str | None, taken: PackStudioError, missing: PackStudioError) -> None:
    """Условие записи «создать или поправить» (`PackFilesService.put`)."""
    if if_match is None:
        if current is not None:
            raise taken
        return
    if current is None:
        raise missing
    if not etag_matches(if_match, current):
        raise PackStudioError(
            PackStudioErrorCode.stale_file,
            etag=file_etag(current),
            content=current.decode("utf-8", errors="replace"),
        )


def apply_yaml_ops(editor: IYamlEditor, text: str, ops: Sequence[YamlOp]) -> str:
    """Набор точечных правок по порядку; невыполнимая это `yaml_patch_conflict` с номером правки."""
    return _apply(editor, text, ops)


def _apply(editor: IYamlEditor, text: str, ops: Sequence[YamlOp]) -> str:
    if len(ops) > MAX_YAML_OPS:
        raise PackStudioError(PackStudioErrorCode.yaml_patch_conflict, op=MAX_YAML_OPS, reason="too many operations")
    for index, op in enumerate(ops):
        try:
            text = _apply_one(editor, text, op)
        except ValueError as exc:  # YamlEditError тоже ValueError
            raise PackStudioError(PackStudioErrorCode.yaml_patch_conflict, op=index, reason=str(exc)[:300]) from None
    return text


def _apply_one(editor: IYamlEditor, text: str, op: YamlOp) -> str:
    if op.op == "set":
        return editor.set_value(text, op.path, op.value)
    if op.op == "delete":
        return editor.delete(text, op.path)
    if op.op == "insert" and op.index is not None:
        return editor.insert_item(text, op.path, op.index, op.value)
    if op.op == "move" and op.index is not None and op.to is not None:
        return editor.move_item(text, op.path, op.index, op.to)
    raise ValueError(f"unsupported operation {op.op!r}")
