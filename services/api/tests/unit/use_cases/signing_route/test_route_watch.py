"""Наблюдатель за изменениями проекта и его хуки (docs/design/signing-route.md, раздел 5.5).

Очередь сверок (`RouteWatch`), хук записи состояния подписей (`WatchedSignatureRepository`), хуки синхронизации и
восстановления и регистрация периодической сверки.
"""

from __future__ import annotations

import asyncio
import contextvars
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.config.signing_route import SigningRouteConfig
from hse_doc_studio.api.observability.install_signing import install_signing_route_sweep
from hse_doc_studio.core.background import PeriodicTask
from hse_doc_studio.core.enums import VcsRestoreMode
from hse_doc_studio.core.projects.volume import UnsafePathError
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.core.vcs.entities import VcsRestoreResult
from hse_doc_studio.infra.vcs.folder_locks import VcsFolderLocks
from hse_doc_studio.use_cases.git_sync.sync_apply import ApplyKind, ApplyOutcome
from hse_doc_studio.use_cases.git_sync.sync_project import SyncProjectUC
from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler
from hse_doc_studio.use_cases.signing_route.watch import (
    RouteWatch,
    WatchedSignatureRepository,
    expect_recalculation,
    own_writes,
    recalculation_done,
)
from hse_doc_studio.use_cases.vcs.restore_vcs import RestoreVcsInput, RestoreVcsUC

from tests.factories import make_project

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PROJECT = uuid4()
OTHER = uuid4()
EMPTY = SignaturesState(slots={}, placements={})


class _Reconcile:
    """Сверка проекта: запоминает вызовы; `gate` держит её, пока тест не отпустит."""

    def __init__(self) -> None:
        self.calls: list[UUID] = []
        self.gate: asyncio.Event | None = None
        self.fail_once = False
        self.contexts: list[str] = []

    async def __call__(self, project_id: UUID) -> None:
        self.calls.append(project_id)
        self.contexts.append(_request.get())
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_once:
            self.fail_once = False
            raise OSError("project unreadable")


_request: contextvars.ContextVar[str] = contextvars.ContextVar("test_request", default="none")


class _Watch:
    def __init__(self) -> None:
        self.projects: list[UUID] = []

    def on_project_changed(self, project_id: UUID) -> None:
        self.projects.append(project_id)


# --- очередь сверок ---------------------------------------------------------------------------------------------------


async def test__route_watch__change__one_reconciliation_in_its_own_task() -> None:
    reconcile = _Reconcile()
    watch = RouteWatch(reconcile)

    watch.on_project_changed(PROJECT)
    # Хук ничего не ждёт и не считает сам: сверка ещё не началась.
    assert reconcile.calls == []
    await watch.drain()

    assert reconcile.calls == [PROJECT]


async def test__route_watch__changes_during_reconciliation__one_more_pass_not_a_queue() -> None:
    reconcile = _Reconcile()
    reconcile.gate = asyncio.Event()
    watch = RouteWatch(reconcile)

    watch.on_project_changed(PROJECT)
    await asyncio.sleep(0)
    for _ in range(5):
        watch.on_pdf_built(PROJECT, "report", 12)
    watch.on_project_changed(OTHER)
    reconcile.gate.set()
    await watch.drain()

    # Пять сборок за время сверки дали один повторный проход; другой проект сверяется сам по себе.
    assert sorted(reconcile.calls, key=str) == sorted([PROJECT, PROJECT, OTHER], key=str)


async def test__route_watch__reconciliation_fails__next_change_is_still_reconciled() -> None:
    reconcile = _Reconcile()
    reconcile.fail_once = True
    watch = RouteWatch(reconcile)

    watch.on_project_changed(PROJECT)
    await watch.drain()
    watch.on_project_changed(PROJECT)
    await watch.drain()

    assert reconcile.calls == [PROJECT, PROJECT]


async def test__route_watch__runs_outside_the_request_context() -> None:
    reconcile = _Reconcile()
    watch = RouteWatch(reconcile)

    # Актор и транзакция запроса живут в контексте: сверка их не наследует, у неё свои.
    _request.set("request with an actor and an open transaction")
    watch.on_project_changed(PROJECT)
    await watch.drain()

    assert reconcile.contexts == ["none"]


async def test__route_watch__called_from_a_worker_thread__scheduled_on_the_app_loop() -> None:
    reconcile = _Reconcile()
    watch = RouteWatch(reconcile)

    # Применение синхронизации и запись подписей идут в рабочем потоке (`asyncio.to_thread`).
    await asyncio.to_thread(watch.on_project_changed, PROJECT)
    await asyncio.sleep(0)
    await watch.drain()

    assert reconcile.calls == [PROJECT]


def test__route_watch__no_event_loop__change_is_dropped_quietly() -> None:
    reconcile = _Reconcile()

    RouteWatch(reconcile).on_project_changed(PROJECT)

    assert reconcile.calls == []


# --- хук записи состояния подписей ------------------------------------------------------------------------------------


class _Signatures:
    def __init__(self) -> None:
        self.saved: list[Path] = []

    def get_state(self, project_folder: Path) -> SignaturesState:
        return EMPTY

    def save_state(self, project_folder: Path, state: SignaturesState) -> None:
        self.saved.append(project_folder)


def _id_of(folder: Path) -> UUID:
    if folder.name == "elsewhere":
        raise UnsafePathError(str(folder))
    return PROJECT


def test__watched_signatures__state_saved__watch_notified_with_the_project() -> None:
    inner, watch = _Signatures(), _Watch()
    repo = WatchedSignatureRepository(inner, _id_of, watch)

    assert repo.get_state(Path("/projects/p")) == EMPTY
    repo.save_state(Path("/projects/p"), EMPTY)

    assert inner.saved == [Path("/projects/p")]
    assert watch.projects == [PROJECT]


def test__watched_signatures__folder_outside_the_volume__saved_without_a_hook() -> None:
    inner, watch = _Signatures(), _Watch()

    WatchedSignatureRepository(inner, _id_of, watch).save_state(Path("/tmp/elsewhere"), EMPTY)  # noqa: S108

    assert inner.saved == [Path("/tmp/elsewhere")]  # noqa: S108
    assert watch.projects == []


def test__watched_signatures__route_writes_its_own_state__hook_is_silent() -> None:
    inner, watch = _Signatures(), _Watch()
    repo = WatchedSignatureRepository(inner, _id_of, watch)

    # Сценарий маршрута сам обновляет снимок: его запись сверку не зовёт (повторный вход).
    with own_writes():
        repo.save_state(Path("/projects/p"), EMPTY)
    assert watch.projects == []
    repo.save_state(Path("/projects/p"), EMPTY)

    assert len(inner.saved) == 2
    assert watch.projects == [PROJECT]


def test__watched_signatures__slot_signing_entry__silent_until_the_route_is_recalculated() -> None:
    inner, watch = _Signatures(), _Watch()
    repo = WatchedSignatureRepository(inner, _id_of, watch)

    def request() -> None:
        # Вход подписи слота маршрута: запись подписи, затем пересчёт маршрута самим входом.
        expect_recalculation()
        repo.save_state(Path("/projects/p"), EMPTY)
        assert watch.projects == []
        recalculation_done()
        repo.save_state(Path("/projects/p"), EMPTY)

    contextvars.copy_context().run(request)
    # Отметка живёт в контексте запроса и наружу не выходит.
    repo.save_state(Path("/projects/p"), EMPTY)

    assert watch.projects == [PROJECT, PROJECT]


# --- хуки восстановления и синхронизации ------------------------------------------------------------------------------


class _Index:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list_known(self) -> list[Path]:
        return [self._folder]


class _Projects:
    def __init__(self, project: Any) -> None:
        self._project = project

    def get(self, folder: Path) -> Any:
        return self._project if folder == self._project.folder else None


class _Vcs:
    def is_available(self, _project: Any) -> bool:
        return True

    def restore(self, _project: Any, **_kw: Any) -> VcsRestoreResult:
        return VcsRestoreResult(restored_from="a" * 40, new_snapshot_id="b" * 40, pre_snapshot_id=None, files_changed=1)


class _Changelog:
    def append(self, _folder: Path, _entry: Any) -> None:
        return None


async def test__restore_from_history__route_watch_notified(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    watch = _Watch()
    uc = RestoreVcsUC(_Projects(project), _Index(tmp_path), _Vcs(), _Changelog(), VcsFolderLocks(), watch)  # type: ignore[arg-type]

    await uc.execute(RestoreVcsInput(project_id=project.id, commit_id="a" * 40, mode=VcsRestoreMode.snapshot))

    assert watch.projects == [project.id]


class _Applier:
    def apply(self, _project: Any, _state: Any, _sync_id: str, _theirs: str | None = None) -> ApplyOutcome:
        return ApplyOutcome(kind=ApplyKind.merged)


class _States:
    def get(self, _folder: Path) -> None:
        return None


class _Reader:
    def current_branch(self, _folder: Path) -> str:
        return "main"


class _Remotes:
    def read(self, _project: Any) -> None:
        return None


class _Operations:
    def update(self, _operation_id: str, **_kw: Any) -> None:
        return None


class _Dispatcher:
    def has_active_for_folder(self, _folder: Path) -> bool:
        return False


async def test__sync_applied__route_watch_notified(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    watch = _Watch()
    uc = SyncProjectUC(
        get_project=None,  # type: ignore[arg-type]
        applier=_Applier(),  # type: ignore[arg-type]
        reader=_Reader(),  # type: ignore[arg-type]
        transport=None,  # type: ignore[arg-type]
        store_remotes=_Remotes(),  # type: ignore[arg-type]
        state_repo=_States(),  # type: ignore[arg-type]
        operations=_Operations(),  # type: ignore[arg-type]
        locks=VcsFolderLocks(),
        dispatcher=_Dispatcher(),  # type: ignore[arg-type]
        policy=None,  # type: ignore[arg-type]
        fetch_book=None,  # type: ignore[arg-type]
        route_watch=watch,
    )

    applied = await uc.import_ref(project, "op", "sync", "refs/hse/import")

    assert applied.kind is ApplyKind.merged
    assert watch.projects == [project.id]


# --- периодическая сверка ---------------------------------------------------------------------------------------------


class _Runner:
    def __init__(self) -> None:
        self.tasks: list[PeriodicTask] = []

    def register(self, task: PeriodicTask) -> None:
        self.tasks.append(task)


class _Reconciler:
    def __init__(self) -> None:
        self.sweeps = 0

    async def sweep(self) -> int:
        self.sweeps += 1
        return 1


class _Container:
    """Контейнер приложения: сверка берёт сценарий в своём запросном окружении."""

    def __init__(self, reconciler: _Reconciler) -> None:
        self._reconciler = reconciler
        self.scopes = 0
        self.open = 0

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[_Container]:
        self.scopes += 1
        self.open += 1
        try:
            yield self
        finally:
            self.open -= 1

    async def get(self, port: object) -> _Reconciler:
        assert port is RouteReconciler
        assert self.open == 1
        return self._reconciler


async def test__install_signing_route_sweep__registers_periodic_task_that_sweeps_in_its_own_scope() -> None:
    app = FastAPI()
    app.state.background = _Runner()
    cfg = Settings(signing_route=SigningRouteConfig(sweep_interval_s=60))
    reconciler = _Reconciler()
    container = _Container(reconciler)

    install_signing_route_sweep(app, container, cfg)  # type: ignore[arg-type]

    (task,) = app.state.background.tasks
    assert (task.name, task.interval_s, task.run_on_start) == ("signing_route_sweep", 60.0, False)
    await task.run()
    await task.run()
    assert (reconciler.sweeps, container.scopes, container.open) == (2, 2, 0)


def test__signing_route_settings__sweep_every_five_minutes_by_default() -> None:
    assert Settings().signing_route.sweep_interval_s == 300.0
    with pytest.raises(ValueError, match="sweep_interval_s"):
        SigningRouteConfig(sweep_interval_s=1)
