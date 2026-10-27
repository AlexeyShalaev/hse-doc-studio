"""Живые ответы настоящего API против контракта git-sync: фронтенд подключается именно к ним.

Сценарий проходит весь путь двух Студий (подключение, отправка, получение, расхождение, конфликты, ошибки доступа) и
снимает ответ каждого состояния. Каждый ответ обязан пройти строгую модель из api/schemas/git_sync.py и содержать все
её поля; нормализованные тела лежат в contracts/git-sync/live, их форму сверяет этот тест, а разбирает zod-тест
фронтенда (entities/git-sync/api/liveContract.test.ts). Расхождение бэкенда с контрактом падает здесь, расхождение
фронтенда с бэкендом падает там.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.git_sync.entities import OperationKind, SyncHealth
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitSyncStateRepository

from tests.fixtures.git_remote import BareRemote, make_bare_remote, seed_remote
from tests.integration.api.git_sync.live_capture import (
    Capture,
    compare_snapshots,
    update_requested,
    write_snapshots,
)
from tests.integration.api.git_sync.studios import PROJECT_FILE, TRACKED_FILE, Studio, when, with_line
from tests.unit.contract.test_git_sync_contract import _SCHEMAS  # noqa: PLC2701 — одни и те же модели у обоих тестов

pytestmark = [pytest.mark.integration, pytest.mark.timeout(240)]

_REPO = Path(__file__).resolve().parents[6]
_SECRET = "demo-token-0123456789"  # noqa: S105 — выдуманный токен: его не должно быть ни в одном ответе
_PLAN = "notes/plan.md"
_OLD = "notes/old.txt"
_DIAGRAM = "figures/diagram.png"
_PLAN_BASE = "# План\n\n1. Обзор\n2. Постановка задачи\n3. Эксперименты\n4. Выводы\n"
_REQUIRED_STATES = {
    "no_remote",
    "unfetched",
    "up_to_date",
    "ahead",
    "behind",
    "diverged",
    "syncing",
    "conflicts",
    "auth_failed",
    "offline",
    "error",
    "blocked",
}
_REQUIRED_OUTCOMES = {"pushed", "fast_forwarded", "merged", "conflicts"}


class Rec:
    """Запросы одной Студии, у которых ответ сразу снимается в `Capture`."""

    def __init__(self, capture: Capture, studio: Studio) -> None:
        self.capture = capture
        self.studio = studio

    async def call(self, method: str, url: str, schema: str, name: str, *, expect: int = 200, **kwargs: Any) -> Any:
        resp = await self.studio.client.request(method, url, **kwargs)
        assert resp.status_code == expect, f"{method} {url}: {resp.status_code} {resp.text}"
        body = resp.json() if resp.content else None
        if schema:
            self.capture.add(schema, name, body, _SCHEMAS)
        return body

    def project(self, tail: str) -> str:
        return self.studio.url(tail).rstrip("/")

    async def status(self, name: str | None = None) -> dict[str, Any]:
        resp = await self.studio.client.get(self.project(""))
        assert resp.status_code == 200, resp.text
        body: dict[str, Any] = resp.json()
        if name:
            self.capture.add("GitStatus", name, body, _SCHEMAS)
        return body

    async def wait_operation(self, operation_id: str, name: str | None = None) -> dict[str, Any]:
        operation = await self.studio.wait(operation_id)
        resp = await self.studio.client.get(f"/api/v1/git/operations/{operation.id}")
        body: dict[str, Any] = resp.json()
        if name:
            self.capture.add("Operation", name, body, _SCHEMAS)
        return body

    async def sync(self, name: str, *, record_started: bool = False) -> dict[str, Any]:
        started = await self.call(
            "POST",
            self.project("sync"),
            "OperationStarted" if record_started else "",
            f"{name}_started",
            expect=202,
            json={},
        )
        return await self.wait_operation(started["operation_id"], name)


def _fetch(studio: Studio, remote: BareRemote) -> None:
    """То, что делает выборка: обновить отслеживаемую ветку (запрос POST /fetch ограничен окном в 15 секунд)."""
    studio.git("fetch", "--quiet", remote.url, "refs/heads/main:refs/remotes/origin/main")


async def _set_health(studio: Studio, health: SyncHealth) -> None:
    states = await studio.get(IGitSyncStateRepository)
    current = states.get(studio.folder)
    assert current is not None
    states.save(studio.folder, replace(current, health=health))


@dataclass
class Scenario:
    """Путь двух Студий по фазам; каждая фаза снимает ответы своих состояний."""

    capture: Capture
    anna: Studio
    boris: Studio
    tmp: Path
    remote: BareRemote
    a: Rec = field(init=False)
    b: Rec = field(init=False)

    def __post_init__(self) -> None:
        self.a = Rec(self.capture, self.anna)
        self.b = Rec(self.capture, self.boris)

    def error(self, name: str, resp: Any, status: int) -> None:
        assert resp.status_code == status, resp.text
        self.capture.add("GitErrorBody", name, resp.json(), _SCHEMAS)

    # --- общие ответы: профиль, секреты, доступы, серверы --------------------------------------------------------

    async def general(self) -> None:
        a = self.a
        await a.call("GET", "/api/v1/profile", "Profile", "live_custom")
        await a.call("GET", "/api/v1/git/secrets/status", "SecretsStatus", "live_ok")
        await a.call("GET", "/api/v1/git/credentials", "GitCredentialList", "live_empty")
        await a.call("GET", "/api/v1/git/hosts", "GitHostList", "live_empty")
        await a.call("GET", "/api/v1/git/host-settings", "GitHostSettingsList", "live_empty")
        folder = {"folder": str(self.tmp)}
        await a.call("GET", "/api/v1/git/shared-folder", "SharedFolder", "live_not_detected", params=folder)
        await a.call("GET", "/api/v1/git/clone/defaults", "CloneDefaults", "live_default", params={"name": "Диплом"})
        created = await a.call(
            "POST",
            "/api/v1/git/credentials",
            "GitCredential",
            "live_pat",
            expect=201,
            json={"kind": "pat", "label": "Токен", "host": "git.example.org", "token": _SECRET},
        )
        await a.call("GET", "/api/v1/git/credentials", "GitCredentialList", "live_one")
        await a.call(
            "PATCH",
            f"/api/v1/git/credentials/{created['id']}",
            "GitCredential",
            "live_renamed",
            json={"label": "Рабочий токен"},
        )
        invalid = await self.anna.client.put("/api/v1/profile", json={"name": "", "email": "не почта"})
        assert invalid.status_code == 422
        self.capture.add("ProfileValidationError", "live_invalid", invalid.json(), _SCHEMAS)

    # --- проект без репозитория: проверка адресов, подключение, первая отправка ----------------------------------

    async def connect(self) -> None:
        a, anna = self.a, self.anna
        empty = make_bare_remote(self.tmp / "remotes" / "empty.git")
        plain = make_bare_remote(self.tmp / "remotes" / "plain.git")
        seed_remote(plain, {"README.md": "# Просто репозиторий\n"})
        await anna.create_project()
        await a.status("live_no_remote")
        await a.call("GET", a.project("contents"), "GitContents", "live_fresh")
        probe = "/api/v1/git/remote/probe"
        await a.call("POST", probe, "Probe", "live_empty", json={"url": empty.url})
        await a.call("POST", probe, "Probe", "live_not_studio", json={"url": plain.url})
        await a.call("POST", probe, "Probe", "live_unreachable", json={"url": f"file://{self.tmp / 'nowhere.git'}"})
        unknown = await anna.client.put(
            a.project("remote"), json={"url": self.remote.url, "credential_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
        )
        self.error("live_credentials_missing", unknown, 409)
        await anna.put(_PLAN, _PLAN_BASE)
        await anna.put(_OLD, "Черновые заметки\nвторая строка\n")
        anna.write(_DIAGRAM, b"\x89PNG\r\n\x00base-diagram")
        anna.commit_dated("Заготовка плана", when(1))
        body = {"url": self.remote.url, "credential_id": None}
        await a.call("PUT", a.project("remote"), "GitStatus", "live_connected_ahead", json=body)
        settings = {"auto_fetch": True, "interval_s": 600}
        await a.call("PATCH", a.project("settings"), "GitStatus", "live_settings", json=settings)

    async def push(self) -> None:
        """Идущая операция, ответ «занято» и успешная отправка."""
        a, anna = self.a, self.anna
        operations = await anna.get(IGitOperationRegistry)
        running = operations.begin(OperationKind.sync, project_id=UUID(anna.id), folder=anna.folder)
        await a.status("live_syncing")
        await a.call("GET", f"/api/v1/git/operations/{running.id}", "Operation", "live_running")
        self.error("live_sync_busy", await anna.client.post(a.project("sync"), json={}), 409)
        operations.finish(running.id)
        pushed = await a.sync("live_sync_pushed", record_started=True)
        assert pushed["result"]["outcome"] == "pushed"
        await a.status("live_up_to_date")

    # --- второй участник: клонирование и история -----------------------------------------------------------------

    async def clone(self) -> None:
        a, b, boris = self.a, self.b, self.boris
        target = {"url": self.remote.url, "folder": str(self.tmp / "boris" / "work" / "thesis")}
        started = await b.call(
            "POST", "/api/v1/git/clone", "OperationStarted", "live_clone_started", expect=202, json=target
        )
        cloned = await b.wait_operation(started["operation_id"], "live_clone_done")
        assert cloned["status"] == "succeeded"
        shown = await boris.client.get(f"/api/v1/projects/{cloned['result']['project_id']}")
        boris.project = shown.json()
        await a.call("GET", f"/api/v1/projects/{self.anna.id}/vcs/history/facets", "HistoryFacets", "live_facets")
        pushed = next(c for c in await self.anna.history() if c["sync"] == "pushed")
        self.capture.add("HistoryCommit", "live_pushed", pushed, _SCHEMAS)
        nowhere = {"url": f"file://{self.tmp / 'nowhere.git'}", "folder": str(self.tmp / "boris" / "work" / "other")}
        failing = await b.call(
            "POST", "/api/v1/git/clone", "OperationStarted", "live_clone_failing", expect=202, json=nowhere
        )
        failed = await b.wait_operation(failing["operation_id"], "live_clone_failed")
        assert failed["status"] == "failed"

    async def behind(self) -> None:
        """Борис пишет и отправляет, Анна видит новое и перематывается."""
        a, anna = self.a, self.anna
        await self.boris.put("notes/boris-1.md", "# Заметка Бориса\n")
        assert (await self.b.sync("live_sync_pushed_by_colleague"))["result"]["outcome"] == "pushed"
        _fetch(anna, self.remote)
        assert (await a.status("live_behind"))["ui_state"] == "behind"
        incoming = next(c for c in await anna.history(sync="incoming") if c["sync"] == "incoming")
        self.capture.add("HistoryCommit", "live_incoming", incoming, _SCHEMAS)
        assert (await a.sync("live_sync_fast_forwarded"))["result"]["outcome"] == "fast_forwarded"

    # --- расхождение: разные места, те же строки, удаление против правки -----------------------------------------

    async def diverge(self) -> None:
        a, anna, boris = self.a, self.anna, self.boris
        await anna.put(TRACKED_FILE, with_line(anna.read(TRACKED_FILE), 3, "% Анна: введение переписано"))
        await anna.put(_PLAN, with_line(_PLAN_BASE, 4, "2. Постановка задачи: версия Анны"))
        await self._rename(anna, "Диплом: версия Анны")
        assert (await anna.client.delete(f"/api/v1/projects/{anna.id}/files/{_OLD}")).status_code == 204
        anna.write(_DIAGRAM, b"\x89PNG\r\n\x00anna-diagram")
        anna.commit_dated("Анна: схема и удаление черновика", when(2))
        ahead = await a.status("live_ahead")
        assert ahead["ui_state"] == "ahead"
        unpushed = next(c for c in await anna.history() if c["sync"] == "unpushed")
        self.capture.add("HistoryCommit", "live_unpushed", unpushed, _SCHEMAS)

        await boris.put(TRACKED_FILE, with_line(boris.read(TRACKED_FILE), 15, "% Борис: пояснение дописано"))
        await boris.put(_PLAN, with_line(_PLAN_BASE, 4, "2. Постановка задачи: версия Бориса"))
        await self._rename(boris, "Диплом: версия Бориса")
        await boris.put(_OLD, "Черновые заметки\nвторая строка\nБорис дописал третью\n")
        boris.write(_DIAGRAM, b"\x89PNG\r\n\x00boris-diagram-newer")
        boris.commit_dated("Борис: схема и правки", when(3))
        assert (await self.b.sync("live_sync_pushed_after_edits"))["result"]["outcome"] == "pushed"
        _fetch(anna, self.remote)
        assert (await a.status("live_diverged"))["ui_state"] == "diverged"

    @staticmethod
    async def _rename(studio: Studio, name: str) -> None:
        resp = await studio.client.patch(f"/api/v1/projects/{studio.id}", json={"name": name})
        assert resp.status_code == 200, resp.text

    async def conflicts(self) -> None:
        a, anna = self.a, self.anna
        assert (await a.sync("live_sync_conflicts"))["result"]["outcome"] == "conflicts"
        assert (await a.status("live_conflicts"))["ui_state"] == "conflicts"
        session = await a.call("GET", a.project("conflicts"), "ConflictSession", "live_session")
        by_path = {f["path"]: f for f in session["files"]}
        assert [by_path[p]["kind"] for p in (PROJECT_FILE, _PLAN, _DIAGRAM)] == ["json", "text", "binary"]
        details = ((_PLAN, "live_text"), (PROJECT_FILE, "live_json"), (_OLD, "live_delete"), (_DIAGRAM, "live_binary"))
        for path, name in details:
            await a.call("GET", a.project("conflicts/file"), "ConflictFileDetail", name, params={"path": path})
        for view in ("ours", "theirs", "result"):
            params = {"path": _PLAN, "view": view}
            await a.call("GET", a.project("conflicts/diff"), "ConflictDiff", f"live_{view}", params=params)

        premature = {"fingerprint": session["fingerprint"], "resolutions": {}, "push": True}
        self.error(
            "live_unresolved_conflicts", await anna.client.post(a.project("conflicts/resolve"), json=premature), 422
        )
        resolutions = await self._decisions(session)
        await a.call("PUT", a.project("conflicts/draft"), "", "", expect=204, json={"resolutions": resolutions})
        await a.call("GET", a.project("conflicts"), "ConflictSession", "live_session_with_draft")
        final = {"fingerprint": session["fingerprint"], "resolutions": None, "push": True}
        started = await a.call(
            "POST", a.project("conflicts/resolve"), "OperationStarted", "live_resolve_started", expect=202, json=final
        )
        resolved = await a.wait_operation(started["operation_id"], "live_resolve_done")
        assert resolved["status"] == "succeeded", resolved
        assert resolved["result"]["outcome"] == "merged"
        await a.status("live_after_resolve")
        merge = next(c for c in await anna.history() if c["is_merge"])
        self.capture.add("HistoryCommit", "live_merge", merge, _SCHEMAS)

    async def _decisions(self, session: dict[str, Any]) -> dict[str, Any]:
        """Решение по каждому конфликтному файлу: свои части в тексте, чужие поля в project.json, чужой файл целиком."""
        resolutions: dict[str, Any] = {}
        for item in session["files"]:
            if item["action"] != "conflict":
                continue
            detail = await self.anna.conflict_detail(item["path"])
            if detail.kind == "text":
                hunks = {seg.key: {"choice": "mine"} for seg in detail.segments if seg.type == "hunk"}
                resolutions[item["path"]] = {"kind": "hunks", "hunks": hunks}
            elif detail.kind == "json":
                fields = {f.pointer: {"choice": "theirs"} for f in detail.fields if f.status == "conflict"}
                resolutions[item["path"]] = {"kind": "fields", "fields": fields}
            else:
                resolutions[item["path"]] = {"kind": "file", "choice": "theirs"}
        return resolutions

    # --- состояние связи: отказ доступа, нет связи, ошибка, нет выборки, чужая ветка -----------------------------

    async def health(self) -> None:
        a, anna = self.a, self.anna
        cases = (
            (SyncHealth.unauthenticated, "auth_failed", "live_auth_failed"),
            (SyncHealth.offline, "offline", "live_offline"),
            (SyncHealth.error, "error", "live_error"),
        )
        for health, state, name in cases:
            await _set_health(anna, health)
            assert (await a.status(name))["ui_state"] == state
        await _set_health(anna, SyncHealth.ok)
        anna.git("update-ref", "-d", "refs/remotes/origin/main")
        assert (await a.status("live_unfetched"))["ui_state"] == "unfetched"
        _fetch(anna, self.remote)
        anna.git("branch", "draft")
        anna.git("symbolic-ref", "HEAD", "refs/heads/draft")
        assert (await a.status("live_blocked_off_branch"))["ui_state"] == "blocked"
        anna.git("symbolic-ref", "HEAD", "refs/heads/master")

    async def ci(self) -> None:
        a = self.a
        request = {"provider": "github", "docs": "all", "publish": "artifacts", "triggers": ["push"]}
        await a.call("POST", a.project("ci/preview"), "CiPreview", "live_github", json=request)
        await a.call(
            "POST", a.project("ci/write"), "CiWrite", "live_github_written", json={**request, "overwrite": False}
        )
        await a.call("GET", a.project("contents"), "GitContents", "live_with_history")


async def test__live_responses__every_state_conforms_to_the_contract(
    anna: Studio, boris: Studio, tmp_path: Path
) -> None:
    capture = Capture(root=str(tmp_path))
    scenario = Scenario(capture, anna, boris, tmp_path, make_bare_remote(tmp_path / "remotes" / "origin.git"))

    await scenario.general()
    await scenario.connect()
    await scenario.push()
    await scenario.clone()
    await scenario.behind()
    await scenario.diverge()
    await scenario.conflicts()
    await scenario.health()
    await scenario.ci()

    items = capture.items
    states = {body["ui_state"] for (schema, _), body in items.items() if schema == "GitStatus"}
    assert states >= _REQUIRED_STATES, sorted(_REQUIRED_STATES - states)
    outcomes = {
        body["result"]["outcome"]
        for (schema, _), body in items.items()
        if schema == "Operation" and body["result"] and "outcome" in body["result"]
    }
    assert outcomes >= _REQUIRED_OUTCOMES, sorted(_REQUIRED_OUTCOMES - outcomes)
    for (schema, name), body in items.items():
        assert _SECRET not in json.dumps(body, ensure_ascii=False), f"{schema}/{name}: в ответе секрет"

    if update_requested():
        write_snapshots(_REPO, items)
    assert compare_snapshots(_REPO, items) == [], "обновить снимки: HSE_UPDATE_LIVE=1 pytest <этот файл>"
