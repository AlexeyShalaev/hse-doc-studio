"""«Диск» раннера по настоящим адресам на Postgres: админка и «Мои раннеры», права, аудит, уведомление, сводка."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.jobs.codec import decode
from hse_doc_studio.core.jobs.disk import RunnerDiskReport, disk_cleanable_bytes

from tests.integration.api.personal.conftest import Person, Stand

pytestmark = pytest.mark.pg

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"
_RUNNER_API = "/api/runner/v1"


def _report(name: str = "docker") -> dict[str, Any]:
    return dict(json.loads((_FIXTURES / "RunnerDiskReportBody" / f"{name}.json").read_text(encoding="utf-8")))


def _cleanable(name: str = "docker") -> int:
    return disk_cleanable_bytes(decode(RunnerDiskReport, _report(name)))


def _announce(stand: Stand, runner: dict[str, str], features: list[str]) -> None:
    response = stand.client.post(
        f"{_RUNNER_API}/announce",
        json={
            "name": "r",
            "version": "0.22.0",
            "tags": ["tex"],
            "concurrency": 1,
            "ai_concurrency": 0,
            "host_kind": "cli",
            "features": ["announce", *features],
            "ai_endpoints": [],
        },
        headers=runner,
    )
    assert response.status_code == 200, response.text


def _disk_runner(stand: Stand, owner: Person, report: str = "docker") -> tuple[dict[str, str], str]:
    runner = stand.personal_runner(owner)
    runner_id = runner.pop("X-Runner-Id")
    _announce(stand, runner, ["control", "disk"])
    sent = stand.client.post(f"{_RUNNER_API}/disk", json=_report(report), headers=runner)
    assert sent.status_code == 204, sent.text
    return runner, runner_id


def _finish(stand: Stand, runner: dict[str, str], freed: int = 4096) -> None:
    polled = stand.client.post(f"{_RUNNER_API}/control/poll", json={"wait_s": 0}, headers=runner).json()
    assert polled["command"] is not None
    progress = {
        "steps": [{"kind": "build_cache", "ref": None, "status": "done", "freed_bytes": freed, "error": None}],
        "freed_bytes": freed,
        "error": None,
    }
    done = stand.client.post(
        f"{_RUNNER_API}/control/{polled['command']['id']}/progress",
        json={"state": "done", "progress": progress},
        headers=runner,
    )
    assert done.status_code == 200, done.text


async def _audit(stand: Stand, action: str) -> list[dict[str, Any]]:
    from hse_doc_studio.infra.db.orm.auth import AuditLogRow  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    async with stand.sessions.use() as db:
        rows = (await db.execute(select(AuditLogRow).where(AuditLogRow.action == action))).scalars().all()
        return [{"actor_id": r.actor_id, "target": r.target, "details": r.details} for r in rows]


async def test__owner_and_admin__disk_rights_cleanup_audit_and_owner_notice(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")
    runner, runner_id = _disk_runner(stand, anna)
    admin = stand.admin()
    mine = f"/api/v1/account/runners/{runner_id}/disk"
    theirs = f"/api/admin/runners/{runner_id}/disk"

    own = stand.client.get(mine, headers=anna.headers)
    assert own.status_code == 200, own.text
    view = own.json()
    assert (view["supported"], view["online"], view["can_clean"], view["can_include_rollback"]) == (
        True,
        True,
        True,
        True,
    )
    assert view["personal_owner"] is None
    assert view["report"]["targets"] == _report()["targets"]
    assert own.headers["Cache-Control"] == "no-store"

    seen = admin.get(theirs).json()
    assert (seen["can_include_rollback"], seen["personal_owner"]) == (False, {"id": anna.id, "name": "anna"})
    # Чужой личный раннер для другого человека не существует, админка ему тоже не видна.
    assert stand.client.get(f"/api/v1/account/runners/{runner_id}/disk", headers=boris.headers).status_code == 404
    assert stand.client.get(theirs, headers=boris.headers).status_code == 404

    rollback = admin.post(f"{theirs}/cleanup", json={"targets": ["old_versions"], "include_rollback": True})
    assert (rollback.status_code, rollback.json()["code"]) == (403, "forbidden")
    invalid = admin.post(f"{theirs}/cleanup", json={"targets": ["build_cache"], "include_rollback": True})
    assert (invalid.status_code, invalid.json()["code"]) == (422, "input_invalid")

    started = admin.post(f"{theirs}/cleanup", json={"targets": ["build_cache"], "include_rollback": False})
    assert started.status_code == 202, started.text
    command = started.json()
    assert (command["kind"], command["state"], command["targets"]) == ("disk.cleanup", "queued", ["build_cache"])
    assert command["created_by"] is not None
    busy = stand.client.post(
        f"{mine}/cleanup", json={"targets": ["runner_cache"], "include_rollback": False}, headers=anna.headers
    )
    assert (busy.status_code, busy.json()["code"]) == (409, "runner_disk_busy")
    assert stand.client.post(f"{mine}/refresh", headers=anna.headers).json()["code"] == "runner_disk_busy"

    _finish(stand, runner)

    after = stand.client.get(mine, headers=anna.headers).json()
    assert (after["command"]["id"], after["command"]["state"]) == (command["id"], "done")
    assert after["command"]["progress"]["freed_bytes"] == 4096
    (queued,) = await _audit(stand, "runner.disk_cleanup")
    assert queued["details"]["targets"] == ["build_cache"]
    assert queued["details"]["owner_id"] == anna.id
    (cleaned,) = await _audit(stand, "runner.disk_cleaned")
    assert (cleaned["target"], cleaned["details"]["state"], cleaned["details"]["freed_bytes"]) == (
        runner_id,
        "done",
        4096,
    )
    inbox = stand.client.get("/api/v1/account/notifications", headers=anna.headers).json()["items"]
    (notice,) = [n for n in inbox if n["kind"] == "runner_disk_cleaned"]
    assert (notice["payload"]["ref_id"], notice["payload"]["outcome"], notice["payload"]["freed_bytes"]) == (
        runner_id,
        "done",
        4096,
    )

    # Свою очистку владелец запускает сам, с откатом; уведомления себе нет, остановка в журнале.
    own_run = stand.client.post(
        f"{mine}/cleanup", json={"targets": ["old_versions"], "include_rollback": True}, headers=anna.headers
    )
    assert own_run.status_code == 202, own_run.text
    stopped = stand.client.post(f"{mine}/commands/{own_run.json()['id']}/cancel", headers=anna.headers)
    assert (stopped.status_code, stopped.json()["state"]) == (200, "cancelled")
    again = stand.client.post(f"{mine}/commands/{own_run.json()['id']}/cancel", headers=anna.headers)
    assert (again.status_code, again.json()["code"]) == (409, "command_finished")
    assert len(await _audit(stand, "runner.disk_cleanup_cancel")) == 1
    inbox = stand.client.get("/api/v1/account/notifications", headers=anna.headers).json()["items"]
    assert len([n for n in inbox if n["kind"] == "runner_disk_cleaned"]) == 1

    measure = stand.client.post(f"{mine}/refresh", headers=anna.headers)
    assert (measure.status_code, measure.json()["kind"], measure.json()["targets"]) == (202, "disk.measure", [])
    assert stand.client.get(mine, headers=anna.headers).json()["measuring"] is True


async def test__lists_carry_disk_brief_and_summary_counts_shared_runners(stand: Stand) -> None:
    anna = await stand.person("anna")
    _, runner_id = _disk_runner(stand, anna, "kubernetes")
    old = stand.personal_runner(anna, "old")
    old_id = old.pop("X-Runner-Id")
    admin = stand.admin()

    mine = {r["id"]: r["disk"] for r in stand.client.get("/api/v1/account/runners", headers=anna.headers).json()}
    assert mine[runner_id]["supported"] is True
    assert mine[runner_id]["cleanable_bytes"] == _cleanable("kubernetes")
    assert mine[old_id] == {"supported": False, "cleanable_bytes": None, "measured_at": None}
    listed = {r["id"]: r["disk"] for r in admin.get("/api/admin/runners").json()["items"]}
    assert listed[runner_id]["cleanable_bytes"] == _cleanable("kubernetes")

    # Сводка «Хранилища» только по общим раннерам: личный в неё не входит.
    summary = admin.get("/api/admin/runners/disk-summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["reporting"] == 0
    assert summary.json()["min_version"] == "0.22.0"
    assert stand.client.get("/api/admin/runners/disk-summary", headers=anna.headers).status_code == 404

    unavailable = admin.post(
        f"/api/admin/runners/{runner_id}/disk/cleanup", json={"targets": ["build_cache"], "include_rollback": False}
    )
    assert (unavailable.status_code, unavailable.json()["code"]) == (409, "disk_target_unavailable")
    outdated = admin.post(f"/api/admin/runners/{old_id}/disk/refresh")
    assert (outdated.status_code, outdated.json()["code"]) == (409, "runner_disk_unsupported")
    assert admin.get(f"/api/admin/runners/{old_id}/disk").json()["reason"] == "outdated"

    assert admin.delete(f"/api/admin/runners/{runner_id}").status_code == 204
    assert admin.get(f"/api/admin/runners/{runner_id}/disk").status_code == 404
    (gone,) = [r for r in admin.get("/api/admin/runners").json()["items"] if r["id"] == runner_id]
    assert gone["disk"] is None
