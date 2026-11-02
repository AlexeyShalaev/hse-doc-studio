"""Сценарии апдейтера на фейковом docker-хосте: успех, отмена до остановки, откат с восстановлением и без, сбой отката.

Часть сценариев идёт через настоящий `UpdateService` (транспорт без HTTP): так проверяется вся цепочка
«решение api -> исполнитель -> события -> итог в журнале запусков».
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.server_update.entities import ReleaseInfo, RunStatus
from hse_doc_studio.infra.update.server_updater.client import ApiUnavailableError
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig
from hse_doc_studio.infra.update.server_updater.engine import Engine
from hse_doc_studio.infra.update.server_updater.journal import Journal
from hse_doc_studio.use_cases.server_update.service import EventReport, PollReport, UpdateService

from tests.fakes.docker_stack import REPO, FakeHost, digest_doc
from tests.unit.use_cases.server_update.test_update_service import Env, configure, make

DIGEST_URL = "https://github.com/x/releases/download/v0.4.0/image-digest.json"


class ServiceApi:
    """Транспорт апдейтера прямо в сервис; `down` имитирует недоступный api (на время обновления он гаснет)."""

    def __init__(self, service: UpdateService) -> None:
        self.service = service
        self.down = False
        self.events: list[dict[str, Any]] = []
        self.pending: list[tuple[str, EventReport]] = []

    def poll(self, *, busy: bool) -> dict[str, Any] | None:
        raise NotImplementedError

    def post_event(self, run_id: str, event: dict[str, Any]) -> None:
        if self.down:
            raise ApiUnavailableError("down")
        self.events.append(event)
        status = RunStatus(event["status"]) if event.get("status") else None
        report = EventReport(
            seq=event["seq"],
            at=datetime.fromisoformat(event["at"]),
            phase=event["phase"],
            level=event["level"],
            message=event["message"],
            status=status,
            from_revision=event.get("from_revision"),
            to_revision=event.get("to_revision"),
            db_restored=event.get("db_restored"),
            error_code=event.get("error_code"),
        )
        self.pending.append((run_id, report))


class Rig:
    """Синхронный движок + асинхронный сервис: события копятся и применяются `await rig.apply()`."""

    def __init__(self, tmp: Path, env: Env, host: FakeHost, *, verify: str = "digest") -> None:
        self.env = env
        self.host = host
        self.api = ServiceApi(env.service)
        self.clock = 0.0
        self.pages: dict[str, tuple[int, str]] = {DIGEST_URL: (200, digest_doc())}
        self.health_ok = True
        config = UpdaterConfig(
            api_url="http://api:8000",
            token="t",
            data_dir=tmp / "updater",
            project="stack",
            snapshot_volume="vol",
            env_file=tmp / ".env",
            health_url="http://api:8000/health/ready",
            health_timeout_s=60,
            stable_s=4,
            min_free_bytes=0,
        )
        (tmp / ".env").write_text("TAG=0.3.1\nOTHER=1\n", encoding="utf-8", newline="\n")
        self.config = config
        self.journal = Journal(config.data_dir / "journal.json")
        self.engine = self._engine()
        self.verify = verify

    def _engine(self) -> Engine:
        def sleep(s: float) -> None:
            self.clock += s

        return Engine(
            self.config,
            self.host,
            self.api,  # type: ignore[arg-type]
            self.journal,
            http_get=self._get,
            sleep=sleep,
            monotonic=lambda: self.clock,
        )

    def _get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if url in self.pages:
            return self.pages[url]
        return (200, "{}") if self.health_ok and self.host.stack_healthy else (503, "")

    async def request(self, *, version: str = "0.4.0") -> dict[str, Any]:
        env = self.env
        await configure(env)
        env.source.answer = type(env.source.answer)(
            releases=(ReleaseInfo(version, digests_url=DIGEST_URL), ReleaseInfo("0.3.1")), checked=True
        )
        await env.service.check_now("boss")
        await env.service.poll(PollReport(updater_version="t", busy=True))
        await env.service.request_update("boss", version)
        spec = await env.service.poll(PollReport())
        assert spec is not None
        return {
            "run_id": spec.run_id,
            "kind": spec.kind.value,
            "from_version": spec.from_version,
            "to_version": spec.to_version,
            "verify": self.verify,
            "digests_url": spec.digests_url,
            "restore_db": spec.restore_db,
        }

    async def apply(self) -> None:
        pending, self.api.pending = self.api.pending, []
        for run_id, report in pending:
            await self.env.service.report(run_id, report)

    async def final(self, spec: dict[str, Any]) -> Any:
        await self.apply()
        run = await self.env.runs.get(spec["run_id"])
        assert run is not None
        return run


@pytest.fixture
def host(tmp_path: Path) -> FakeHost:
    return FakeHost(tmp_path / "updater")


async def test__success__migrates_swaps_images_and_reports_revisions(tmp_path: Path, host: FakeHost) -> None:
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.succeeded
    assert (run.from_revision, run.to_revision) == ("r1", "r2")
    assert host.versions() == {"api": "sha256:new", "runner": "sha256:new"}
    assert host.db_rev == "r2"
    # прежний образ сохранён под тегом отката, TAG в .env продвинут, остальные строки целы
    assert host.refs[f"{REPO}:rollback-prev"] == "sha256:old"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "TAG=0.4.0\nOTHER=1\n"
    assert rig.journal.run is None
    assert rig.journal.data["last_ok"]["snapshot"]
    phases = [e["phase"] for e in rig.api.events]
    assert phases.index("snapshot") < phases.index("pull") < phases.index("stop") < phases.index("migrate")
    assert phases.index("migrate") < phases.index("restart") < phases.index("health")


async def test__unhealthy_new_version_with_schema_change_restores_snapshot_and_rolls_back(
    tmp_path: Path, host: FakeHost
) -> None:
    host.new_image_healthy = False
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.db_restored is True
    assert run.error_code == "health_timeout"
    assert host.db_rev == "r1", "схема возвращена из снимка: старый образ не запустится на r2 (db-ahead)"
    assert host.versions() == {"api": "sha256:old", "runner": "sha256:old"}
    assert host.stack_healthy
    assert (tmp_path / ".env").read_text(encoding="utf-8").startswith("TAG=0.3.1")
    assert any(p.outcome == "update_rolled_back" for _u, _k, p, _d in rig.env.notifier.sent)  # type: ignore[attr-defined]
    assert rig.journal.run is None


async def test__unhealthy_new_version_without_schema_change_rolls_back_without_restore(
    tmp_path: Path,
) -> None:
    host = FakeHost(tmp_path / "updater", old_rev="r1", new_rev="r1")
    host.new_image_healthy = False
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.db_restored is False
    assert not any(a[:3] == ["run", "--rm", "--network"] and "restore-snapshot" in a for a in host.log)
    assert host.stack_healthy


async def test__failed_migration_rolls_back_and_restores_when_schema_moved(tmp_path: Path, host: FakeHost) -> None:
    host.migration_ok = False
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.error_code == "migration_failed"
    assert host.stack_healthy
    assert host.versions()["api"] == "sha256:old"


async def test__snapshot_failure_cancels_before_anything_is_stopped(tmp_path: Path, host: FakeHost) -> None:
    host.snapshot_ok = False
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "snapshot_failed"
    assert not any(a[0] == "stop" for a in host.log), "ничего не останавливали"
    assert host.stack_healthy


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("pull", "pull_failed"),
        ("digest", "digest_mismatch"),
        ("nodoc", "digest_missing"),
        ("cosign", "signature_invalid"),
    ],
)
async def test__verification_failures_cancel_the_run(tmp_path: Path, host: FakeHost, setup: str, code: str) -> None:
    rig = Rig(tmp_path, make(current="0.3.1"), host, verify="cosign" if setup == "cosign" else "digest")
    spec = await rig.request()
    if setup == "pull":
        host.pull_ok = False
    elif setup == "digest":
        rig.pages[DIGEST_URL] = (200, digest_doc(digest="sha256:" + "b" * 64))
    elif setup == "nodoc":
        rig.pages[DIGEST_URL] = (404, "")
    else:
        host.cosign_ok = False

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == code
    assert not any(a[0] == "stop" for a in host.log)
    assert host.versions()["api"] == "sha256:old"


async def test__verify_off_installs_without_a_published_digest(tmp_path: Path, host: FakeHost) -> None:
    rig = Rig(tmp_path, make(current="0.3.1"), host, verify="none")
    spec = await rig.request()
    rig.pages[DIGEST_URL] = (404, "")
    rig.engine.execute(spec)
    assert (await rig.final(spec)).status is RunStatus.succeeded


async def test__rollback_failure_is_reported_as_failed_with_a_hand_hint(tmp_path: Path, host: FakeHost) -> None:
    host.new_image_healthy = False
    host.restore_ok = False
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.failed
    assert run.error_code == "restore_failed"
    assert "snapshots/" in (run.error or "")
    assert any(p.outcome == "update_failed" for _u, _k, p, _d in rig.env.notifier.sent)  # type: ignore[attr-defined]


async def test__events_survive_an_api_outage_and_arrive_in_order(tmp_path: Path, host: FakeHost) -> None:
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()
    rig.api.down = True

    rig.engine.execute(spec)
    assert rig.journal.outbox, "пока api не отвечает, события лежат в журнале"
    assert rig.api.events == []

    rig.api.down = False
    rig.engine.flush()
    run = await rig.final(spec)
    assert run.status is RunStatus.succeeded
    assert not rig.journal.outbox
    assert [e.seq for e in run.events if e.seq] == sorted(e.seq for e in run.events if e.seq)


async def test__crash_after_stop_is_rolled_back_on_restart(tmp_path: Path, host: FakeHost) -> None:
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()
    # имитируем смерть апдейтера сразу после остановки сервисов и миграции
    rig.journal.start_run(
        {
            "id": spec["run_id"],
            "kind": "update",
            "to_version": "0.4.0",
            "from_version": "0.3.1",
            "phase": "migrate",
            "seq": 5,
            "stopped": True,
            "migrating": True,
            "from_rev": "r1",
            "snapshot": f"{spec['run_id']}.pgdump",
            "old": {
                k: {"id": "sha256:old", "ref": f"{REPO}:0.3.1", "name": host.services[k]["name"]} for k in host.services
            },
        }
    )
    (rig.config.data_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    host.snapshot_rev = "r1"
    host.db_rev = "r2"
    for svc in host.services.values():
        svc["running"] = False

    rig._engine().recover()  # noqa: SLF001
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.error_code == "updater_restarted"
    assert host.db_rev == "r1"
    assert host.stack_healthy
    assert rig.journal.run is None


async def test__manual_rollback_after_success_restores_previous_images_and_snapshot(
    tmp_path: Path, host: FakeHost
) -> None:
    env = make(current="0.3.1")
    rig = Rig(tmp_path, env, host)
    spec = await rig.request()
    rig.engine.execute(spec)
    assert (await rig.final(spec)).status is RunStatus.succeeded

    # приложение теперь на 0.4.0: просим откат
    from hse_doc_studio.core.server_update.options import UpdateOptions

    env.service._options = UpdateOptions(current_version="0.4.0", executor_enabled=True)  # noqa: SLF001
    await env.service.poll(PollReport(busy=True))
    run = await env.service.request_rollback("boss", restore_db=True)
    spec2 = await env.service.poll(PollReport())
    assert spec2 is not None
    assert spec2.run_id == run.id

    rig.engine.execute(
        {
            "run_id": spec2.run_id,
            "kind": "rollback",
            "from_version": "0.4.0",
            "to_version": "0.3.1",
            "verify": "none",
            "digests_url": "",
            "restore_db": True,
        }
    )
    done = await rig.final({"run_id": spec2.run_id})

    assert done.status is RunStatus.succeeded
    assert host.db_rev == "r1"
    assert host.versions() == {"api": "sha256:old", "runner": "sha256:old"}
    assert (tmp_path / ".env").read_text(encoding="utf-8").startswith("TAG=0.3.1")
    assert rig.journal.data["last_ok"] is None


async def test__unsupported_container_options_stop_the_run_before_any_change(tmp_path: Path, host: FakeHost) -> None:
    original = host.container

    def privileged(key: str) -> dict[str, Any]:
        data = original(key)
        data["HostConfig"]["Privileged"] = True
        return data

    host.container = privileged  # type: ignore[method-assign]
    rig = Rig(tmp_path, make(current="0.3.1"), host)
    spec = await rig.request()
    rig.engine.execute(spec)
    run = await rig.final(spec)
    assert run.status is RunStatus.cancelled
    assert run.error_code == "unsupported_container_options"
