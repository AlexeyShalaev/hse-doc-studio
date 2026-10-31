"""Порты git по HTTPS: запуск upload-pack и receive-pack в режиме stateless-rpc."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.git_remote.entities import GitService, PushPolicy


class GitBodyTooLargeError(Exception):
    """Тело запроса больше предела (MAX_PUSH_BYTES): процесс git остановлен."""


class GitBodyInvalidError(Exception):
    """Тело запроса не разбирается (повреждённый gzip)."""


@dataclass(frozen=True)
class GitRpcOutcome:
    """Итог процесса git после потока: код выхода и хвост stderr (для журнала, не для клиента)."""

    returncode: int | None
    stderr_tail: str
    timed_out: bool = False


class IGitSmartHttp(Protocol):
    async def advertise(self, service: GitService, git_dir: Path, *, protocol: str | None) -> bytes:
        """Ответ `info/refs?service=...`: строка сервиса (кроме протокола v2) и реклама ссылок."""
        ...

    def rpc(  # noqa: PLR0913 — параметры одного запуска git
        self,
        service: GitService,
        git_dir: Path,
        body: AsyncIterator[bytes],
        *,
        gzip: bool,
        protocol: str | None,
        extra_config: Sequence[str] = (),
        extra_env: Mapping[str, str] | None = None,
        outcome: list[GitRpcOutcome] | None = None,
    ) -> AsyncIterator[bytes]:
        """Поток ответа `git-<service>`; тело клиента идёт в stdin процесса. Отмена потока убивает процесс.

        В `outcome` (если дан) по завершении кладётся итог процесса.
        """
        ...


@dataclass(frozen=True)
class PushHookSession:
    """Что нужно процессу `git receive-pack` для приёма: `-c` с хуками и окружение с файлом политики."""

    extra_config: tuple[str, ...]
    extra_env: Mapping[str, str]
    policy_file: Path


class IPushRuntime(Protocol):
    def prepare(
        self, policy: PushPolicy, *, git_dir: Path, work_tree: Path, actor_id: str, lang: str, max_input_bytes: int
    ) -> PushHookSession:
        """Файл политики (0600) и аргументы приёма; файл удаляет `cleanup`."""
        ...

    def cleanup(self, session: PushHookSession) -> None: ...
    async def head(self, git_dir: Path) -> str | None: ...
    async def branch(self, git_dir: Path) -> str | None: ...
    async def changed_paths(self, git_dir: Path, old: str, new: str) -> list[str]: ...


class IExternalChangeReconciler(Protocol):
    async def after_external_change(self, project_id: UUID, folder: Path, *, project_json_changed: bool) -> None:
        """Файлы проекта сменились мимо API (push): права из БД обратно в project.json, копия каталога, кэши."""
        ...
