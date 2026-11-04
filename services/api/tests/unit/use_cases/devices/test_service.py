"""Присутствие и видимость устройств по правам (docs/design/connected-devices.md, раздел 8)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.devices.entities import (
    AiState,
    DeviceActivity,
    EndpointReport,
    Presence,
    ProjectReport,
    SyncCode,
)
from hse_doc_studio.infra.devices.registry import PresenceRegistry
from hse_doc_studio.use_cases.devices.service import (
    MAX_DEVICES_PER_USER,
    DevicesOverviewUC,
    ForgetDeviceUC,
    ListAccountDevicesUC,
    ProjectStudiosUC,
    RecordHeartbeatUC,
    TooManyDevicesError,
)

from tests.unit.use_cases.devices.fakes import (
    CONFIG,
    PROJECT,
    Clock,
    MemoryAcl,
    MemoryDevices,
    MemoryProviders,
    MemoryRunners,
    MemoryUsers,
    actor,
    builder,
    provider,
    report,
    runner,
    stored,
    user,
)


def heartbeat(devices: MemoryDevices, registry: PresenceRegistry, clock: Clock) -> RecordHeartbeatUC:
    return RecordHeartbeatUC(devices, registry, CONFIG, clock=clock)  # type: ignore[arg-type]


async def test__heartbeat__identical_signals_write_the_database_rarely() -> None:
    clock, devices, registry = Clock(), MemoryDevices(), PresenceRegistry()
    uc = heartbeat(devices, registry, clock)

    receipts = []
    for _ in range(5):
        receipts.append(await uc.execute("anna", "tok", report()))
        clock.advance(seconds=60)

    # 5 сигналов за 4 минуты: запись на первом (0 с), на третьем (120 с) и на пятом (240 с).
    assert devices.writes == 3
    assert [r.persisted for r in receipts] == [True, False, True, False, True]
    assert (receipts[0].interval_s, receipts[0].online_window_s) == (60, 180)


async def test__heartbeat__state_change_is_written_immediately_and_keeps_first_seen() -> None:
    clock, devices, registry = Clock(), MemoryDevices(), PresenceRegistry()
    uc = heartbeat(devices, registry, clock)
    await uc.execute("anna", "tok", report())
    first = devices.rows[("anna", "a" * 32)].first_seen_at
    clock.advance(seconds=10)

    await uc.execute("anna", "tok", report(activity=DeviceActivity.building))

    stored_row = devices.rows[("anna", "a" * 32)]
    assert devices.writes == 2
    assert stored_row.report.activity is DeviceActivity.building
    assert stored_row.first_seen_at == first


async def test__heartbeat__person_cannot_exceed_the_device_limit() -> None:
    clock, devices, registry = Clock(), MemoryDevices(), PresenceRegistry()
    uc = heartbeat(devices, registry, clock)
    for n in range(MAX_DEVICES_PER_USER):
        await uc.execute("anna", "tok", report(f"{n:032x}"))

    with pytest.raises(TooManyDevicesError):
        await uc.execute("anna", "tok", report("f" * 32))
    # Уже известное устройство продолжает работать, а чужой человек свои 20 не делит с Анной.
    await uc.execute("anna", "tok", report(f"{0:032x}", activity=DeviceActivity.syncing))
    await uc.execute("boris", "tok", report("f" * 32))


async def test__heartbeat__silent_devices_are_forgotten_after_retention() -> None:
    clock, devices, registry = Clock(), MemoryDevices(), PresenceRegistry()
    uc = heartbeat(devices, registry, clock)
    await uc.execute("anna", "tok", report("1" * 32))
    clock.advance(days=CONFIG.retention_days + 1)

    await uc.execute("anna", "tok", report("2" * 32))

    assert set(devices.rows) == {("anna", "2" * 32)}


async def test__view__online_by_window_and_memory_overlay_beats_stale_database_row() -> None:
    clock, registry = Clock(), PresenceRegistry()
    devices = MemoryDevices()
    devices.rows[("anna", "a" * 32)] = stored("anna", report(), seen=clock.now)
    view = builder(clock, runners=MemoryRunners(runner()), registry=registry)

    clock.advance(seconds=181)
    offline = (await view.build("anna", await devices.list_for_user("anna")))[0]
    registry.observe("anna", report(), clock.now, 120)
    online = (await view.build("anna", await devices.list_for_user("anna")))[0]

    assert offline.presence is Presence.offline
    assert online.presence is Presence.online
    assert online.last_seen_at == clock.now


async def test__view__runner_comes_from_the_server_table_not_from_what_the_studio_claims() -> None:
    clock = Clock()
    devices = [stored("boris", report(runner_id="r1"))]
    # r1 принадлежит Анне: Борис, назвавший чужой раннер, его не получает.
    view = builder(clock, runners=MemoryRunners(runner("r1", owner="anna")))

    result = (await view.build("boris", devices))[0]

    assert result.runner is None
    assert result.ai.state is AiState.runner_unpaired


async def test__view__runner_state_tags_and_busy_flag_for_the_owner() -> None:
    clock = Clock()
    busy = replace(report(), runner=replace(report().runner, running_jobs=2))  # type: ignore[type-var]
    view = builder(clock, runners=MemoryRunners(runner("r1", owner="anna")))

    result = (await view.build("anna", [stored("anna", busy)]))[0]

    assert result.runner is not None
    assert (result.runner.state, result.runner.tags, result.runner.busy) == ("online", ("ai", "tex"), True)


@pytest.mark.parametrize(
    ("providers", "endpoints", "enabled", "paused", "expected"),
    [
        ((provider(),), (EndpointReport("ollama", "ollama", True, ("m",)),), True, False, AiState.ready),
        ((), (EndpointReport("ollama", "ollama", True, ("m",)),), True, False, AiState.no_provider),
        ((provider(),), (EndpointReport("ollama", "ollama", False, ()),), True, False, AiState.endpoint_unreachable),
        ((provider(),), (EndpointReport("ollama", "ollama", True, ()),), True, False, AiState.no_models),
        ((provider(),), (EndpointReport("ollama", "ollama", True, ("m",)),), False, False, AiState.disabled),
        ((provider(),), (EndpointReport("ollama", "ollama", True, ("m",)),), True, True, AiState.runner_paused),
    ],
)
async def test__view__ai_state_explains_why_the_cloud_can_or_cannot_use_the_studio_model(
    providers: tuple, endpoints: tuple[EndpointReport, ...], enabled: bool, paused: bool, expected: AiState
) -> None:
    clock = Clock()
    view = builder(
        clock,
        runners=MemoryRunners(runner(paused=paused)),
        providers=MemoryProviders(*providers),
        enabled=enabled,
    )

    result = (await view.build("anna", [stored("anna", report(endpoints=endpoints))]))[0]

    assert result.ai.state is expected


async def test__view__offline_studio_reports_studio_offline_for_ai() -> None:
    clock = Clock()
    view = builder(clock, runners=MemoryRunners(runner()), providers=MemoryProviders(provider()))
    device = stored("anna", report())
    clock.advance(minutes=10)

    result = (await view.build("anna", [device]))[0]

    assert result.ai.state is AiState.studio_offline


async def test__view__project_sync_is_attached_only_when_a_project_is_asked() -> None:
    clock = Clock()
    rep = report(projects=(ProjectReport(PROJECT, SyncCode.ahead, ahead=3, last_sync_at=clock.now, auto_sync=True),))
    view = builder(clock, runners=MemoryRunners(runner()))

    plain = (await view.build("anna", [stored("anna", rep)]))[0]
    asked = (await view.build("anna", [stored("anna", rep)], project_id=PROJECT))[0]

    assert plain.project is None
    assert asked.project is not None
    assert (asked.project.sync, asked.project.ahead, asked.project.auto_sync) == (SyncCode.ahead, 3, True)
    assert plain.projects_count == 1


def studios(clock: Clock, devices: MemoryDevices, members: dict[str, Role]) -> ProjectStudiosUC:
    return ProjectStudiosUC(
        devices,  # type: ignore[arg-type]
        builder(clock, runners=MemoryRunners(runner("r1", owner="anna"), runner("r2", owner="boris"))),
        MemoryAcl(members),  # type: ignore[arg-type]
        MemoryUsers(user("anna", "Анна"), user("boris", "Борис"), user("root", "Админ", admin=True)),  # type: ignore[arg-type]
        CONFIG,
    )


async def test__project_studios__owner_sees_own_devices_in_full_and_others_only_as_a_name() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("anna", "a" * 32)] = stored("anna", report("a" * 32), seen=clock.now)
    devices.rows[("boris", "b" * 32)] = stored(
        "boris", report("b" * 32, name="Секретный ноутбук Бориса", runner_id="r2"), seen=clock.now
    )
    uc = studios(clock, devices, {"anna": Role.owner, "boris": Role.editor})

    found = await uc.execute(actor("anna"), PROJECT)

    assert [d.name for d in found.mine] == ["MacBook Анны"]
    assert [(p.user_id, p.name) for p in found.others] == [("boris", "Борис")]
    # У чужой строки нет ни одного поля устройства: имя машины, версия, раннер, модели не раскрываются.
    assert set(vars(found.others[0])) == {"user_id", "name"}


async def test__project_studios__other_studio_is_listed_only_while_online() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=clock.now)
    uc = studios(clock, devices, {"anna": Role.owner, "boris": Role.editor})
    clock.advance(minutes=10)

    found = await uc.execute(actor("anna"), PROJECT)

    assert found.others == ()


async def test__project_studios__person_who_lost_access_disappears_at_once() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=clock.now)
    uc = studios(clock, devices, {"anna": Role.owner})

    found = await uc.execute(actor("anna"), PROJECT)

    assert found.others == ()


async def test__project_studios__instance_admin_gets_nothing_beyond_an_ordinary_member() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=clock.now)
    uc = studios(clock, devices, {"anna": Role.owner, "boris": Role.editor, "root": Role.reader})
    admin = actor("root", "Админ")

    found = await uc.execute(admin, PROJECT)

    assert found.mine == ()
    assert [p.name for p in found.others] == ["Борис"]
    assert set(vars(found.others[0])) == {"user_id", "name"}


async def test__project_studios__own_device_never_appears_in_others() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("anna", "a" * 32)] = stored("anna", report("a" * 32), seen=clock.now)
    uc = studios(clock, devices, {"anna": Role.owner})

    found = await uc.execute(actor("anna"), PROJECT)

    assert found.others == ()
    assert len(found.mine) == 1


async def test__account_devices__lists_only_own_and_forget_removes_only_own() -> None:
    clock, devices, registry = Clock(), MemoryDevices(), PresenceRegistry()
    devices.rows[("anna", "a" * 32)] = stored("anna", report("a" * 32), seen=clock.now)
    devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=clock.now)
    listing = ListAccountDevicesUC(devices, builder(clock, runners=MemoryRunners(runner())), CONFIG)  # type: ignore[arg-type]
    forget = ForgetDeviceUC(devices, registry)  # type: ignore[arg-type]

    mine = await listing.execute(actor("anna"))
    stranger = await forget.execute(actor("anna"), "b" * 32)
    own = await forget.execute(actor("anna"), "a" * 32)

    assert [d.id for d in mine.items] == ["a" * 32]
    assert (stranger, own) == (False, True)
    assert ("boris", "b" * 32) in devices.rows


async def test__overview__shows_this_device_and_the_others_with_the_project_right_checked() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("anna", "a" * 32)] = stored("anna", report("a" * 32), seen=clock.now)
    devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=clock.now)
    members = {"anna": Role.owner, "boris": Role.editor}
    inner = studios(clock, devices, members)
    uc = DevicesOverviewUC(devices, builder(clock, runners=MemoryRunners(runner())), inner, MemoryAcl(members), CONFIG)  # type: ignore[arg-type]

    found = await uc.execute(actor("anna"), "a" * 32, PROJECT)
    outsider = await uc.execute(actor("zoe"), "z" * 32, PROJECT)

    assert found.device is not None
    assert found.device.project is not None
    assert [p.name for p in found.others] == ["Борис"]
    assert outsider.device is None
    assert outsider.others == ()


async def test__overview__reader_without_sources_does_not_see_who_works_on_the_project() -> None:
    clock, devices = Clock(), MemoryDevices()
    devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=clock.now)
    members = {"anna": Role.reader, "boris": Role.editor}
    inner = studios(clock, devices, members)
    reader_acl = MemoryAcl(members, show_sources=False)
    uc = DevicesOverviewUC(devices, builder(clock), inner, reader_acl, CONFIG)  # type: ignore[arg-type]

    found = await uc.execute(actor("anna"), "a" * 32, PROJECT)

    assert found.others == ()
