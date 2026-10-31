import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource, Grant, ProjectAcl, Role
from hse_doc_studio.core.enums import ProjectAccessMode
from hse_doc_studio.core.git_remote.entities import GitService
from hse_doc_studio.core.git_remote.protocols import GitRpcOutcome, PushHookSession
from hse_doc_studio.core.identity.entities import ApiToken, TokenScope
from hse_doc_studio.core.project_access import ProjectAccess
from hse_doc_studio.infra.vcs.folder_locks import VcsFolderLocks
from hse_doc_studio.use_cases.git_remote.auth import GitAccess, GitPrincipal
from hse_doc_studio.use_cases.git_remote.receive import ProjectBusyError, PushLimits, ReceivePushUC

from tests.factories import make_project


@dataclass
class _State:
    access: ProjectAccess


class _ProjectAccess:
    def __init__(self, mode: ProjectAccessMode = ProjectAccessMode.full) -> None:
        self.mode = mode

    async def execute(self, _inp: Any) -> _State:
        return _State(ProjectAccess(mode=self.mode))


class _Operations:
    def __init__(self, busy: bool = False) -> None:
        self.busy = busy

    def is_busy(self, _folder: Path) -> bool:
        return self.busy


class _Vcs:
    def __init__(self) -> None:
        self.commits = 0

    def is_initialized(self, _project: Any) -> bool:
        return True

    def commit(self, _project: Any, **_kw: Any) -> None:
        self.commits += 1


class _Runtime:
    def __init__(self) -> None:
        self.heads = ["a" * 40, "b" * 40]
        self.cleaned = 0

    def prepare(self, _policy: Any, **_kw: Any) -> PushHookSession:
        return PushHookSession((), {}, Path("/tmp/none"))  # noqa: S108

    def cleanup(self, _session: Any) -> None:
        self.cleaned += 1

    async def head(self, _git_dir: Path) -> str | None:
        return self.heads.pop(0)

    async def branch(self, _git_dir: Path) -> str | None:
        return "master"

    async def changed_paths(self, *_args: Any) -> list[str]:
        return [".hse-studio/project.json", "a.tex"]


class _Reconciler:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def after_external_change(self, _pid: Any, _folder: Path, *, project_json_changed: bool) -> None:
        self.calls.append(project_json_changed)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    async def record(self, action: str, **kw: Any) -> None:
        self.events.append((action, kw.get("details")))


def _access(tmp_path: Path) -> GitAccess:
    token = ApiToken("pat", "u1", "t", "h", "p", frozenset({TokenScope.git_write}), datetime.now(UTC))
    principal = GitPrincipal(Actor.user("u1", source=ActorSource.pat), token)
    acl = ProjectAcl(project_id="p", grants={"u1": Grant(Role.owner)})
    return GitAccess(principal, make_project(folder=tmp_path), acl, Grant(Role.owner), GitService.receive_pack)


def _uc(locks: VcsFolderLocks, **overrides: Any) -> tuple[ReceivePushUC, dict[str, Any]]:
    parts: dict[str, Any] = {
        "project_access": _ProjectAccess(),
        "operations": _Operations(),
        "locks": locks,
        "vcs": _Vcs(),
        "runtime": _Runtime(),
        "reconciler": _Reconciler(),
        "audit": _Audit(),
        "limits": PushLimits(max_push_bytes=1000, lock_wait_s=0.05),
    }
    parts.update(overrides)
    return ReceivePushUC(**parts), parts


async def test__begin_finish__snapshot_lock_reconcile_and_audit(tmp_path: Path) -> None:
    locks = VcsFolderLocks()
    uc, parts = _uc(locks)

    session = await uc.begin(_access(tmp_path))
    assert locks.for_folder(tmp_path).locked()  # type: ignore[attr-defined]
    await uc.finish(session, GitRpcOutcome(0, ""))

    assert not locks.for_folder(tmp_path).locked()  # type: ignore[attr-defined]
    assert parts["vcs"].commits == 1
    assert parts["reconciler"].calls == [True]
    action, details = parts["audit"].events[0]
    assert action == "git.push"
    assert details["result"] == "accepted"
    assert details["paths"] == 2
    assert parts["runtime"].cleaned == 1


@pytest.mark.parametrize(
    "override",
    [{"operations": _Operations(busy=True)}, {"project_access": _ProjectAccess(ProjectAccessMode.read_only)}],
)
async def test__begin__busy_or_read_only__project_busy(tmp_path: Path, override: dict[str, Any]) -> None:
    uc, _ = _uc(VcsFolderLocks(), **override)

    with pytest.raises(ProjectBusyError):
        await uc.begin(_access(tmp_path))


async def test__begin__lock_held__waits_then_busy(tmp_path: Path) -> None:
    locks = VcsFolderLocks()
    uc, _ = _uc(locks)

    async with locks.for_folder(tmp_path):
        with pytest.raises(ProjectBusyError):
            await uc.begin(_access(tmp_path))
        with pytest.raises(ProjectBusyError):
            await uc.advertise(_access(tmp_path))
    await asyncio.sleep(0)
