"""Проверки и правила версии шаблона формой (docs/design/template-studio.md, 5.7, срез T14).

Модель это файлы `checks/*.yaml` каталога версии (шапка и правила по индексам) и `checks_version` из `version.yaml`.
Правка идёт под замком пространства с `If-Match` по ETag своего файла (`PackFilesService.edit_yaml`), как у мест
подписей (T9) и точек сдачи (T13): выпущенная версия отвечает `version_released`, чужая правка `stale_file`,
невыполнимая правка `checks_invalid` с причиной по-английски, файл не меняется. Новый файл правил форма создаёт
обычной записью файла (`PUT .../files/...`).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

import yaml

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.checks_form import (
    MAX_CHECKS_OPS,
    ChecksConfig,
    ChecksEditError,
    ChecksFileView,
    ChecksOp,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import VERSION_MANIFEST, VersionRef
from hse_doc_studio.core.pack_studio.protocols import IPackChecksForm
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.preview import version_ref

CHECKS_DIR = "checks"
_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.yaml$")
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


@dataclass(frozen=True)
class ChecksFileState:
    path: str
    name: str
    etag: str
    read_only: str | None
    view: ChecksFileView


@dataclass(frozen=True)
class ChecksConfigState:
    path: str
    etag: str
    read_only: str | None
    config: ChecksConfig


@dataclass(frozen=True)
class ChecksView:
    """Проверки версии: документы ростера, файлы правил и `checks_version`."""

    ref: VersionRef
    documents: tuple[str, ...]
    files: tuple[ChecksFileState, ...]
    config: ChecksConfigState


class PackChecksFormService:
    def __init__(self, files: PackFilesService, editor: IPackChecksForm) -> None:
        self._files = files
        self._editor = editor

    async def get(self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str) -> ChecksView:
        return await self._view(actor, workspace_id, version_ref(pack, template, version))

    async def edit_file(  # noqa: PLR0913 — путь версии, файл, правки и версия файла
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        name: str,
        ops: Sequence[ChecksOp],
        if_match: str | None,
    ) -> ChecksView:
        if not 0 < len(ops) <= MAX_CHECKS_OPS:
            raise PackStudioError(PackStudioErrorCode.checks_invalid, reason=f"1..{MAX_CHECKS_OPS} operations")
        ref = version_ref(pack, template, version)
        path = _checks_path(ref, name)
        await self._files.edit_yaml(
            actor, workspace_id, path, _guarded(lambda text: self._editor.apply_file(text, ops)), if_match
        )
        return await self._view(actor, workspace_id, ref)

    async def edit_config(  # noqa: PLR0913 — путь версии, значение и версия файла
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        config: ChecksConfig,
        if_match: str | None,
    ) -> ChecksView:
        ref = version_ref(pack, template, version)
        manifest = f"{ref.dir}/{VERSION_MANIFEST}"
        await self._files.edit_yaml(
            actor, workspace_id, manifest, _guarded(lambda text: self._editor.apply_config(text, config)), if_match
        )
        return await self._view(actor, workspace_id, ref)

    async def _view(self, actor: Actor, workspace_id: UUID, ref: VersionRef) -> ChecksView:
        manifest = f"{ref.dir}/{VERSION_MANIFEST}"
        found = await self._files.read(actor, workspace_id, manifest)
        text = _text(found.content)
        config = await asyncio.to_thread(self._safe, lambda: self._editor.describe_config(text))
        tree = await self._files.tree(actor, workspace_id)
        prefix = f"{ref.dir}/{CHECKS_DIR}/"
        paths = sorted(
            f.path
            for f in tree.tree.files
            if not f.is_dir
            and f.path.startswith(prefix)
            and "/" not in f.path[len(prefix) :]
            and f.path.endswith(".yaml")
        )
        files: list[ChecksFileState] = []
        for path in paths:
            item = await self._files.read(actor, workspace_id, path)
            name = path[len(prefix) :]
            content = _text(item.content)
            view = await asyncio.to_thread(
                self._safe, lambda c=content, n=name: self._editor.describe_file(c, n.removesuffix(".yaml"))
            )
            files.append(ChecksFileState(path, name, item.etag, item.read_only, view))
        return ChecksView(
            ref=ref,
            documents=_documents(text),
            files=tuple(files),
            config=ChecksConfigState(manifest, found.etag, found.read_only, config),
        )

    @staticmethod
    def _safe[T](describe: Callable[[], T]) -> T:
        try:
            return describe()
        except (TypeError, ValueError) as exc:
            raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None


def _guarded(edit: Callable[[str], str]) -> Callable[[str], str]:
    def run(text: str) -> str:
        try:
            return edit(text)
        except ChecksEditError as exc:
            raise PackStudioError(PackStudioErrorCode.checks_invalid, reason=str(exc)[:300]) from None
        except (TypeError, ValueError) as exc:
            raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None

    return run


def _checks_path(ref: VersionRef, name: str) -> str:
    if not _FILE_NAME.match(name):
        raise PackStudioError(PackStudioErrorCode.path_not_allowed, path=name)
    return f"{ref.dir}/{CHECKS_DIR}/{name}"


def _documents(text: str) -> tuple[str, ...]:
    try:
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик (CSafeLoader или SafeLoader)
    except yaml.YAMLError:
        return ()
    roster = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(roster, list):
        return ()
    ids = (item.get("id") if isinstance(item, dict) else item for item in roster)
    return tuple(doc for doc in ids if isinstance(doc, str))


def _text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise PackStudioError(PackStudioErrorCode.version_unreadable, reason="the file is not UTF-8") from None
