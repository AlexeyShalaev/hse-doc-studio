from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.backup.entities import (
    DestinationKind,
    DestinationSpec,
    EncryptionMode,
    RunStatus,
    RunTrigger,
)
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.schedule import Schedule, ScheduleKind
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.infra.backup.parts import PartFetcher, PartUploader
from hse_doc_studio.use_cases.backup.destinations import (
    CreateDestinationUC,
    DeleteDestinationUC,
    DestinationInput,
    TestDestinationUC,
    UpdateDestinationUC,
)
from hse_doc_studio.use_cases.backup.restore import BackupSource, RestoreBackupUC
from hse_doc_studio.use_cases.backup.runs import DeleteStoredBackupUC, ScheduledBackupTick
from hse_doc_studio.use_cases.backup.service import BackupService, list_backups
from hse_doc_studio.use_cases.backup.settings import GetBackupSettingsUC, UpdateBackupSettingsUC

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.backup import (
    Admins,
    BytesProducer,
    DirStores,
    FixedEnv,
    FixedKeys,
    FixedPlan,
    InMemoryDestinations,
    InMemoryRuns,
    RecordingNotifier,
)
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow, ReversingCipher

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def admin() -> Actor:
    return Actor(id="admin", kind=ActorKind.user, source=ActorSource.session, is_instance_admin=True)


@dataclass
class Env:
    root: Path
    clock: Clock
    destinations: InMemoryDestinations
    runs: InMemoryRuns
    settings: InMemoryInstanceSettingsRepository
    stores: DirStores
    plan: FixedPlan
    keys: FixedKeys
    audit: InMemoryAuditLog
    notifier: RecordingNotifier
    service: BackupService
    cipher: ReversingCipher

    def create_uc(self) -> CreateDestinationUC:
        return CreateDestinationUC(
            self.destinations,
            self.runs,
            self.cipher,
            self.stores,
            self.service,
            self.audit,
            NoopUow(),
            self.clock,  # type: ignore[arg-type]
        )

    async def add_local(self, name: str = "local", path: str = "main", default: bool = False) -> str:
        spec = DestinationSpec(name=name, kind=DestinationKind.local, local_path=path)
        created = await self.create_uc().execute(admin(), DestinationInput(spec, make_default=default))
        return created.id


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    clock = Clock()
    destinations, runs = InMemoryDestinations(), InMemoryRuns()
    settings = InMemoryInstanceSettingsRepository()
    stores = DirStores(tmp_path / "dest")
    plan = FixedPlan(BytesProducer("db.pgdump.enc", b"DUMP" * 1000), BytesProducer("files.tar.enc", b"FILES" * 10))
    keys = FixedKeys()
    audit = InMemoryAuditLog()
    notifier = RecordingNotifier()
    cipher = ReversingCipher()
    service = BackupService(
        destinations,
        runs,
        settings,
        stores,
        PartUploader(tmp_path / "tmp"),
        plan,
        FixedEnv(),
        keys,
        cipher,  # type: ignore[arg-type]
        audit,
        notifier,
        Admins("admin", "admin2"),
        clock=clock,  # type: ignore[arg-type]
    )
    yield Env(tmp_path, clock, destinations, runs, settings, stores, plan, keys, audit, notifier, service, cipher)
    await service.drain()


async def test__run__writes_encrypted_parts_and_manifest_last(env: Env) -> None:
    dest_id = await env.add_local()
    run = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id="admin")
    assert run.status is RunStatus.ok
    folder = env.root / "dest" / "main" / run.backup_id  # type: ignore[operator]
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["db.pgdump.enc", "files.tar.enc", "manifest.json"]
    assert b"DUMPDUMP" not in (folder / "db.pgdump.enc").read_bytes()
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["app_version"] == "9.9.9"
    assert manifest["installation_id"] == "install-1"
    assert {p["name"] for p in manifest["parts"]} == {"db.pgdump.enc", "files.tar.enc"}
    assert run.size_bytes == sum(p["size"] for p in manifest["parts"])
    assert [e.action for e in env.audit._entries if e.action.startswith("backup.run")] == [  # noqa: SLF001
        "backup.run_start",
        "backup.run_finish",
    ]


async def test__run__restorable_with_same_key_and_not_with_other(env: Env) -> None:
    dest_id = await env.add_local()
    run = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    stored = await env.destinations.get(dest_id)
    assert stored is not None
    store = env.service.open_store(stored)
    uc = RestoreBackupUC(_NoTarget(), PartFetcher(env.root / "fetch"))  # type: ignore[arg-type]
    source = BackupSource(store, run.backup_id or "")
    verified = await uc.load(source, installation_keys=[bytes(range(32))], passphrase=None)
    lines: list[str] = []
    await uc.verify(source, verified, lines.append)
    assert len(lines) == 4
    with pytest.raises(BackupError) as caught:
        await uc.load(source, installation_keys=[bytes(range(1, 33))], passphrase=None)
    assert caught.value.code is BackupErrorCode.secrets_unavailable


class _NoTarget:
    pass


async def test__run__corrupted_part_detected_by_verify(env: Env) -> None:
    dest_id = await env.add_local()
    run = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    folder = env.root / "dest" / "main" / run.backup_id  # type: ignore[operator]
    blob = bytearray((folder / "db.pgdump.enc").read_bytes())
    blob[40] ^= 0xFF
    (folder / "db.pgdump.enc").write_bytes(bytes(blob))
    stored = await env.destinations.get(dest_id)
    assert stored is not None
    uc = RestoreBackupUC(_NoTarget(), PartFetcher(env.root / "fetch"))  # type: ignore[arg-type]
    source = BackupSource(env.service.open_store(stored), run.backup_id or "")
    verified = await uc.load(source, installation_keys=[bytes(range(32))], passphrase=None)
    with pytest.raises(BackupError) as caught:
        await uc.verify(source, verified, lambda _line: None)
    assert caught.value.code is BackupErrorCode.integrity


async def test__run__failure_cleans_up_marks_failed_and_notifies_admins(env: Env) -> None:
    env.plan.producers[1].fail = True  # type: ignore[attr-defined]
    dest_id = await env.add_local()
    run = await env.service.run_and_wait(trigger=RunTrigger.schedule, destination_id=dest_id, actor_id=None)
    assert run.status is RunStatus.failed
    assert "boom" in (run.error or "")
    assert not list((env.root / "dest" / "main").glob("*/*")), "частичный бэкап должен быть убран"
    assert [(u, k, d) for u, k, _p, d in env.notifier.sent] == [
        ("admin", "backup_failed", f"bkf:{run.id}"),
        ("admin2", "backup_failed", f"bkf:{run.id}"),
    ]
    assert env.notifier.sent[0][2].path == "local"  # type: ignore[attr-defined]


async def test__run__failure_without_notification_when_disabled(env: Env) -> None:
    env.plan.producers[0].fail = True  # type: ignore[attr-defined]
    dest_id = await env.add_local()
    await env.settings.set("backup.notify_admins", False, source="admin")
    run = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    assert run.status is RunStatus.failed
    assert env.notifier.sent == []


async def test__run__second_start_while_running_is_rejected(env: Env) -> None:
    dest_id = await env.add_local()
    first = await env.service.start(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    with pytest.raises(BackupError) as caught:
        await env.service.start(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    assert caught.value.code is BackupErrorCode.already_running
    await env.service.drain()
    assert (await env.runs.get(first.id)).status is RunStatus.ok  # type: ignore[union-attr]


async def test__start__without_destination__reports_no_destination(env: Env) -> None:
    with pytest.raises(BackupError) as caught:
        await env.service.start(trigger=RunTrigger.manual, destination_id=None, actor_id=None)
    assert caught.value.code is BackupErrorCode.no_destination


async def test__recover_stale__marks_running_as_interrupted(env: Env) -> None:
    dest_id = await env.add_local()
    await env.runs.start(_run(dest_id))
    assert await env.service.recover_stale() == 1
    assert (await env.runs.running()) is None


def _run(dest_id: str):  # type: ignore[no-untyped-def]
    from hse_doc_studio.core.backup.entities import BackupRun  # noqa: PLC0415

    return BackupRun("stale", dest_id, "local", RunTrigger.schedule, RunStatus.running, None, NOW)


async def test__retention__keeps_last_n_and_removes_older_from_storage(env: Env) -> None:
    dest_id = await env.add_local()
    await env.settings.set("backup.keep_last", 2, source="admin")
    await env.settings.set("backup.keep_days", 0, source="admin")
    ids = []
    for _ in range(4):
        run = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
        ids.append(run.backup_id)
    folders = sorted(p.name for p in (env.root / "dest" / "main").iterdir() if not p.name.startswith("."))
    assert folders == sorted(ids[-2:])
    removed = [r for r in env.runs.items.values() if r.removed_at is not None]
    assert len(removed) == 2
    assert any(e.action == "backup.delete" for e in env.audit._entries)  # noqa: SLF001


async def test__retention__failed_runs_do_not_count(env: Env) -> None:
    dest_id = await env.add_local()
    await env.settings.set("backup.keep_last", 1, source="admin")
    await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    env.plan.producers[0].fail = True  # type: ignore[attr-defined]
    await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    assert len([p for p in (env.root / "dest" / "main").iterdir() if not p.name.startswith(".")]) == 1


async def test__passphrase_mode__requires_phrase_and_encrypts_with_it(env: Env) -> None:
    dest_id = await env.add_local()
    await env.settings.set("backup.encryption_mode", "passphrase", source="admin")
    failed = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    assert failed.status is RunStatus.failed
    assert "passphrase" in (failed.error or "")
    env.keys.phrase = "correct horse battery staple"
    ok = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    assert ok.status is RunStatus.ok
    stored = await env.destinations.get(dest_id)
    assert stored is not None
    listed = await list_backups(env.service.open_store(stored), "")
    assert listed[0].manifest.encryption_mode is EncryptionMode.passphrase
    uc = RestoreBackupUC(_NoTarget(), PartFetcher(env.root / "fetch"))  # type: ignore[arg-type]
    source = BackupSource(env.service.open_store(stored), ok.backup_id or "")
    await uc.load(source, installation_keys=[], passphrase="correct horse battery staple")
    with pytest.raises(BackupError):
        await uc.load(source, installation_keys=[bytes(range(32))], passphrase="wrong wrong wrong wrong")


async def test__scheduler__runs_when_due_and_not_before(env: Env) -> None:
    await env.add_local(default=True)
    tick = ScheduledBackupTick(env.settings, env.service, env.destinations, clock=env.clock)
    assert await tick.run_once() is None, "выключено"
    settings = UpdateBackupSettingsUC(env.settings, env.runs, env.cipher, env.audit, NoopUow(), env.clock)  # type: ignore[arg-type]
    from hse_doc_studio.core.backup.entities import BackupSettings  # noqa: PLC0415

    await settings.execute(admin(), BackupSettings(enabled=True, schedule=Schedule(ScheduleKind.interval, 6)))
    first = await tick.run_once()
    assert first is not None
    assert first.trigger is RunTrigger.schedule
    await env.service.drain()
    assert await tick.run_once() is None, "интервал ещё не прошёл"
    env.clock.now += timedelta(hours=6, minutes=1)
    assert await tick.run_once() is not None
    await env.service.drain()


async def test__scheduler__failed_run_is_not_retried_every_tick(env: Env) -> None:
    await env.add_local(default=True)
    env.plan.producers[0].fail = True  # type: ignore[attr-defined]
    await env.settings.set("backup.enabled", True, source="admin")
    tick = ScheduledBackupTick(env.settings, env.service, env.destinations, clock=env.clock)
    assert await tick.run_once() is not None
    await env.service.drain()
    assert await tick.run_once() is None
    assert len(env.runs.items) == 1


async def test__scheduler__cron_waits_for_firing_after_enabling(env: Env) -> None:
    await env.add_local(default=True)
    update = UpdateBackupSettingsUC(env.settings, env.runs, env.cipher, env.audit, NoopUow(), env.clock)  # type: ignore[arg-type]
    from hse_doc_studio.core.backup.entities import BackupSettings  # noqa: PLC0415

    await update.execute(admin(), BackupSettings(enabled=True, schedule=Schedule(ScheduleKind.cron, cron="0 3 * * *")))
    tick = ScheduledBackupTick(env.settings, env.service, env.destinations, clock=env.clock)
    assert await tick.run_once() is None
    env.clock.now = datetime(2026, 11, 2, 3, 0, 30, tzinfo=UTC)
    assert await tick.run_once() is not None
    await env.service.drain()


async def test__settings__validation_and_secret_handling(env: Env) -> None:
    from hse_doc_studio.core.backup.entities import BackupSettings  # noqa: PLC0415

    update = UpdateBackupSettingsUC(env.settings, env.runs, env.cipher, env.audit, NoopUow(), env.clock)  # type: ignore[arg-type]
    with pytest.raises(BackupError):
        await update.execute(admin(), BackupSettings(encryption_mode=EncryptionMode.passphrase))
    with pytest.raises(BackupError):
        await update.execute(admin(), BackupSettings(), passphrase="short")
    status = await update.execute(
        admin(), BackupSettings(encryption_mode=EncryptionMode.passphrase), passphrase="a long enough phrase"
    )
    assert status.passphrase_set
    assert status.settings.encryption_mode is EncryptionMode.passphrase
    audit = [e for e in env.audit._entries if e.action == "backup.settings_update"][-1]  # noqa: SLF001
    assert "a long enough phrase" not in json.dumps(audit.details, default=str)
    assert await env.settings.get_secret("backup.passphrase") is not None
    with pytest.raises(IdentityError):
        await GetBackupSettingsUC(env.settings, env.runs).execute(
            Actor(id="u", kind=ActorKind.user, source=ActorSource.session)
        )


async def test__destinations__secrets_sealed_hint_only_default_and_audit_clean(env: Env) -> None:
    spec = DestinationSpec(name="S3", kind=DestinationKind.s3, endpoint="http://x:9000", bucket="my-bucket")
    created = await env.create_uc().execute(admin(), DestinationInput(spec, "AKIAEXAMPLE1234", "TOP-SECRET-VALUE"))
    assert created.is_default
    assert created.secret_key_set
    assert created.access_key_hint == "…1234"
    stored = await env.destinations.get(created.id)
    assert stored is not None
    assert "TOP-SECRET-VALUE" not in (stored.secret_key_enc or "")[::-1].replace("TOP", "T-O-P")
    assert stored.secret_key_enc
    assert stored.secret_key_enc.startswith("backup_destinations/secret_key_enc/")
    dumped = json.dumps([e.details for e in env.audit._entries], default=str)  # noqa: SLF001
    assert "TOP-SECRET-VALUE" not in dumped
    assert "AKIAEXAMPLE1234" not in dumped
    opened = env.service.open_secrets(stored)
    assert (opened.access_key, opened.secret_key) == ("AKIAEXAMPLE1234", "TOP-SECRET-VALUE")


async def test__destinations__update_keeps_secrets_when_blank_and_replaces_when_given(env: Env) -> None:
    spec = DestinationSpec(name="S3", kind=DestinationKind.s3, bucket="my-bucket")
    created = await env.create_uc().execute(admin(), DestinationInput(spec, "KEY-ONE-1111", "SECRET-ONE"))
    update = UpdateDestinationUC(
        env.destinations, env.runs, env.cipher, env.stores, env.service, env.audit, NoopUow(), env.clock
    )  # type: ignore[arg-type]
    renamed = DestinationSpec(name="S3 renamed", kind=DestinationKind.s3, bucket="my-bucket", prefix="p")
    await update.execute(admin(), created.id, DestinationInput(renamed))
    stored = await env.destinations.get(created.id)
    assert stored is not None
    assert env.service.open_secrets(stored).secret_key == "SECRET-ONE"
    assert stored.destination.spec.name == "S3 renamed"
    assert stored.destination.last_check_ok is None
    await update.execute(admin(), created.id, DestinationInput(renamed, secret_key="SECRET-TWO"))
    stored = await env.destinations.get(created.id)
    assert stored is not None
    assert env.service.open_secrets(stored).secret_key == "SECRET-TWO"
    assert stored.destination.access_key_hint == "…1111"


async def test__destinations__duplicate_name_and_missing_keys_rejected(env: Env) -> None:
    await env.add_local("one", "a")
    with pytest.raises(BackupError) as dup:
        await env.add_local("ONE", "b")
    assert dup.value.code is BackupErrorCode.conflict
    with pytest.raises(BackupError) as keys:
        await env.create_uc().execute(
            admin(), DestinationInput(DestinationSpec("s", DestinationKind.s3, bucket="my-bucket"))
        )
    assert keys.value.field == "access_key"


async def test__destinations__default_moves_when_deleted(env: Env) -> None:
    first = await env.add_local("one", "a")
    second = await env.add_local("two", "b")
    assert (await env.destinations.get_default()).destination.id == first  # type: ignore[union-attr]
    delete = DeleteDestinationUC(
        env.destinations, env.runs, env.cipher, env.stores, env.service, env.audit, NoopUow(), env.clock
    )  # type: ignore[arg-type]
    await delete.execute(admin(), first)
    assert (await env.destinations.get_default()).destination.id == second  # type: ignore[union-attr]


async def test__test_destination__ok_failure_and_primary_warning(env: Env) -> None:
    uc = TestDestinationUC(
        env.destinations, env.runs, env.cipher, env.stores, env.service, env.audit, NoopUow(), env.clock
    )  # type: ignore[arg-type]
    good = await uc.execute(
        admin(),
        destination_id=None,
        data=DestinationInput(DestinationSpec("l", DestinationKind.local, local_path="probe")),
    )
    assert good.ok
    assert good.warnings == ()
    assert not list((env.root / "dest" / "probe").glob("hse-write-test-*")), "пробный объект удалён"
    env.stores.primary.add("main-bucket")
    warned = await uc.execute(
        admin(),
        destination_id=None,
        data=DestinationInput(DestinationSpec("s", DestinationKind.s3, bucket="main-bucket"), "AK", "SK"),
    )
    assert warned.ok
    assert warned.warnings == ("same_as_primary",)
    bad = await uc.execute(
        admin(),
        destination_id=None,
        data=DestinationInput(DestinationSpec("b", DestinationKind.s3, bucket="broken-bucket"), "AK", "SK"),
    )
    assert not bad.ok
    assert "EndpointConnectionError" in (bad.error or "")


async def test__test_destination__saved_records_result_and_uses_stored_keys(env: Env) -> None:
    spec = DestinationSpec("S3", DestinationKind.s3, bucket="broken-bucket")
    created = await env.create_uc().execute(admin(), DestinationInput(spec, "AK-1234", "SK-9999"))
    uc = TestDestinationUC(
        env.destinations, env.runs, env.cipher, env.stores, env.service, env.audit, NoopUow(), env.clock
    )  # type: ignore[arg-type]
    result = await uc.execute(admin(), destination_id=created.id, data=None)
    assert not result.ok
    stored = await env.destinations.get(created.id)
    assert stored is not None
    assert stored.destination.last_check_ok is False
    assert env.stores.opened[-1].secret_key == "SK-9999"


async def test__delete_stored_backup__removes_objects_and_marks_run(env: Env) -> None:
    dest_id = await env.add_local()
    run = await env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    uc = DeleteStoredBackupUC(env.destinations, env.runs, env.service, env.audit)
    await uc.execute(admin(), dest_id, run.backup_id)  # type: ignore[arg-type]
    assert not list((env.root / "dest" / "main").glob("*/*"))
    assert (await env.runs.get(run.id)).removed_at is not None  # type: ignore[union-attr]
    with pytest.raises(BackupError):
        await uc.execute(admin(), dest_id, "../../etc")


async def test__cancel__marks_run_interrupted_and_cleans_up(env: Env) -> None:
    gate = asyncio.Event()

    class Slow(BytesProducer):
        async def produce(self, writer):  # type: ignore[no-untyped-def]
            writer.write(b"x")
            await gate.wait()
            return {}

    env.plan.producers.insert(0, Slow("db.pgdump.enc", b""))
    dest_id = await env.add_local()
    run = await env.service.start(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    await asyncio.sleep(0.05)
    await env.service.cancel_all()
    assert (await env.runs.get(run.id)).status is RunStatus.interrupted  # type: ignore[union-attr]
