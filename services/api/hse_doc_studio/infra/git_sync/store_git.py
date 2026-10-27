"""Запуск git над хранилищем проекта по пути папки, без доменного `Project`.

Нужен портам синхронизации (они работают с `project_folder`): чтение объектов, запись коммита
слияния. Окружение и жёсткий набор `-c` те же, что у GitVcsService, поэтому чужой config
хранилища и окружение сервера до git не доходят.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsUnavailableError
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir


class StoreGit:
    def __init__(self, author_name: str = "HSE Studio", author_email: str = "bot@hse-studio.local") -> None:
        self._author_name = author_name
        self._author_email = author_email

    def run(
        self,
        folder: Path,
        args: Sequence[str],
        *,
        input_bytes: bytes | None = None,
        env: Mapping[str, str] | None = None,
        author: tuple[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        """`author` подменяет служебную подпись у команд, которые её записывают (commit-tree, update-ref)."""
        name, email = author or (self._author_name, self._author_email)
        cmd = [
            "git",
            "--git-dir",
            str(store_git_dir(folder)),
            "--work-tree",
            str(folder),
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "core.quotepath=false",
            "-c",
            "safe.directory=*",
            *hardened_git_config(),
            *args,
        ]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(folder),
                input=input_bytes,
                capture_output=True,
                check=False,
                env={**base_git_env(), **(env or {})},
            )
        except OSError as exc:
            raise VcsUnavailableError(str(exc)) from exc
        if check and proc.returncode != 0:
            raise VcsCommandError(" ".join(args[:2]), proc.stderr.decode("utf-8", "replace"))
        return proc

    def text(
        self, folder: Path, args: Sequence[str], *, env: Mapping[str, str] | None = None, check: bool = True
    ) -> str:
        return self.run(folder, args, env=env, check=check).stdout.decode("utf-8", "replace")
