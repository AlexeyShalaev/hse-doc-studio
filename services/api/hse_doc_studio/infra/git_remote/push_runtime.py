"""Приём push на стороне процесса git: свои хуки, файл политики и чтение стора до и после приёма.

Хуки берутся из пакета (`infra/git_remote/hooks`) и копируются в личный каталог процесса с правом исполнения:
каталог хуков стора недоверенный, а права файлов в установленном колесе не гарантированы.
"""

from __future__ import annotations

import asyncio
import functools
import os
import shutil
import stat
import sys
import tempfile
import uuid
from importlib import resources
from pathlib import Path

from hse_doc_studio.core.git_remote.entities import PushPolicy
from hse_doc_studio.core.git_remote.protocols import PushHookSession
from hse_doc_studio.core.git_remote.push_policy import policy_to_json
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config

HOOK_NAMES = ("pre-receive", "push-to-checkout")


@functools.lru_cache(maxsize=1)
def hooks_dir() -> Path:
    """Личный каталог процесса только с нашими хуками; другие хуки git не найдёт."""
    target = Path(tempfile.mkdtemp(prefix="hse-studio-push-hooks-"))
    source = resources.files("hse_doc_studio.infra.git_remote") / "hooks"
    for name in HOOK_NAMES:
        path = target / name
        path.write_bytes((source / name).read_bytes())
        path.chmod(stat.S_IRWXU)
    return target


def receive_config(hooks: Path, max_input_bytes: int) -> tuple[str, ...]:
    pairs = (
        "receive.denyCurrentBranch=updateInstead",
        "receive.denyNonFastForwards=true",
        "receive.denyDeletes=true",
        "receive.fsckObjects=true",
        f"receive.maxInputSize={max_input_bytes}",
        "receive.advertisePushOptions=false",
        f"core.hooksPath={hooks}",
    )
    return tuple(arg for pair in pairs for arg in ("-c", pair))


class GitPushRuntime:
    def prepare(  # noqa: PLR0913 — данные одного приёма
        self, policy: PushPolicy, *, git_dir: Path, work_tree: Path, actor_id: str, lang: str, max_input_bytes: int
    ) -> PushHookSession:
        fd, raw = tempfile.mkstemp(prefix=f"push-policy-{uuid.uuid4().hex}-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(policy_to_json(policy))
        os.chmod(raw, stat.S_IRUSR | stat.S_IWUSR)
        env = {
            "HSE_PUSH_POLICY": raw,
            "HSE_PUSH_ACTOR": actor_id,
            "HSE_PUSH_LANG": lang,
            "HSE_PYTHON": sys.executable,
            "HSE_GIT_DIR": str(git_dir),
            "HSE_WORK_TREE": str(work_tree),
        }
        return PushHookSession(receive_config(hooks_dir(), max_input_bytes), env, Path(raw))

    def cleanup(self, session: PushHookSession) -> None:
        session.policy_file.unlink(missing_ok=True)

    async def head(self, git_dir: Path) -> str | None:
        out = await _git(git_dir, "rev-parse", "--verify", "-q", "HEAD")
        return (out.strip() or None) if out is not None else None

    async def branch(self, git_dir: Path) -> str | None:
        out = await _git(git_dir, "symbolic-ref", "--short", "-q", "HEAD")
        return (out.strip() or None) if out is not None else None

    async def changed_paths(self, git_dir: Path, old: str, new: str) -> list[str]:
        out = await _git(git_dir, "diff", "--name-only", "-z", "--no-renames", old, new)
        return [p for p in (out or "").split("\0") if p]


async def _git(git_dir: Path, *args: str) -> str | None:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *hardened_git_config(),
        "-c",
        "safe.directory=*",
        "--git-dir",
        str(git_dir),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=base_git_env(),
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="surrogateescape") if proc.returncode == 0 else None


def remove_hooks_dir() -> None:
    """Для тестов: следующий вызов `hooks_dir` создаст каталог заново."""
    if hooks_dir.cache_info().currsize:
        shutil.rmtree(hooks_dir(), ignore_errors=True)
        hooks_dir.cache_clear()
