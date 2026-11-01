from __future__ import annotations

from hse_doc_studio.core.backup.entities import DestinationKind
from hse_doc_studio.use_cases.backup.destinations import CreateDestinationUC
from hse_doc_studio.use_cases.backup.provision import ProvisionBackupUC, ProvisionPlan, build_plan
from hse_doc_studio.use_cases.backup.settings import UpdateBackupSettingsUC

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.backup import InMemoryDestinations, InMemoryRuns
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow, ReversingCipher


def _plan(**over: object) -> ProvisionPlan:
    args: dict[str, object] = {
        "kind": "local", "name": "main", "local_path": "main", "endpoint": None, "region": "us-east-1",
        "bucket": None, "prefix": "", "path_style": True, "access_key": None, "secret_key": None,
        "schedule_enabled": True, "schedule_kind": "interval", "interval_hours": 12, "cron": "0 3 * * *",
        "keep_last": 5, "keep_days": 10, "encryption_mode": "installation", "passphrase": None,
        "notify_admins": True,
    }  # fmt: skip
    args.update(over)
    return build_plan(**args)  # type: ignore[arg-type]


class _Env:
    def __init__(self) -> None:
        self.destinations = InMemoryDestinations()
        self.settings = InMemoryInstanceSettingsRepository()
        self.audit = InMemoryAuditLog()
        cipher, runs, uow = ReversingCipher(), InMemoryRuns(), NoopUow()
        create = CreateDestinationUC(self.destinations, runs, cipher, None, None, self.audit, uow)  # type: ignore[arg-type]
        update = UpdateBackupSettingsUC(self.settings, runs, cipher, self.audit, uow)  # type: ignore[arg-type]
        self.uc = ProvisionBackupUC(self.destinations, create, update)


async def test__empty_install__creates_default_destination_and_settings() -> None:
    env = _Env()
    assert await env.uc.execute(_plan()) is True
    (dest,) = await env.destinations.list_all()
    assert dest.is_default
    assert dest.spec.kind is DestinationKind.local
    values = await env.settings.get_all()
    assert values["backup.enabled"] is True
    assert values["backup.interval_hours"] == 12
    assert values["backup.keep_last"] == 5


async def test__existing_destination__is_left_alone() -> None:
    env = _Env()
    await env.uc.execute(_plan())
    assert await env.uc.execute(_plan(name="other", keep_last=1)) is False
    assert len(await env.destinations.list_all()) == 1
    assert (await env.settings.get_all())["backup.keep_last"] == 5


async def test__s3_without_keys__is_logged_not_raised() -> None:
    env = _Env()
    assert await env.uc.execute(_plan(kind="s3", bucket="b")) is False
    assert await env.destinations.list_all() == []


async def test__s3_with_keys__stores_encrypted_keys() -> None:
    env = _Env()
    plan = _plan(kind="s3", bucket="backups", endpoint="http://m:9000", access_key="AKIAXXXX1234", secret_key="s3cr3t")
    assert await env.uc.execute(plan) is True
    stored = await env.destinations.get((await env.destinations.list_all())[0].id)
    assert stored is not None
    assert stored.access_key_enc
    assert "s3cr3t" not in str(stored.secret_key_enc)


async def test__passphrase_mode__saves_passphrase() -> None:
    env = _Env()
    plan = _plan(encryption_mode="passphrase", passphrase="a-long-passphrase-1")
    assert await env.uc.execute(plan) is True
    assert (await env.settings.get_all())["backup.encryption_mode"] == "passphrase"
