"""Люди в проекте: сигнал вкладки, объединение вкладок и Студий, права (docs/design/connected-devices.md, 15)."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.collab.colors import person_color
from hse_doc_studio.core.devices.people import Activity, Channel, WebSignal
from hse_doc_studio.infra.collab.manager import CollabIdentity
from hse_doc_studio.infra.devices.registry import PresenceRegistry
from hse_doc_studio.infra.devices.web_registry import WebPresenceRegistry
from hse_doc_studio.use_cases.devices.people import (
    LeaveWebPresenceUC,
    MemberVerdicts,
    ProjectPeopleUC,
    RecordWebPresenceUC,
    VerdictCache,
)
from hse_doc_studio.use_cases.devices.service import DevicesOverviewUC, ProjectStudiosUC

from tests.unit.use_cases.devices.fakes import (
    CONFIG,
    PROJECT,
    Clock,
    MemoryAcl,
    MemoryDevices,
    MemoryUsers,
    actor,
    builder,
    report,
    stored,
    user,
)


class Mono:
    """Монотонные часы для памяти проверок: двигает тест."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Stand:
    def __init__(self, members: dict[str, Role], *, show_sources: bool = True) -> None:
        self.clock = Clock()
        self.mono = Mono()
        self.devices = MemoryDevices()
        self.web = WebPresenceRegistry()
        self.members = members
        verdicts = MemberVerdicts(
            VerdictCache(monotonic=self.mono),
            MemoryAcl(members, show_sources=show_sources),  # type: ignore[arg-type]
            MemoryUsers(user("anna", "Анна Петрова"), user("boris", "Борис Иванов"), user("carol", "Карина")),  # type: ignore[arg-type]
        )
        self.people = ProjectPeopleUC(
            self.web,
            self.devices,
            builder(self.clock, registry=PresenceRegistry()),
            verdicts,
            CONFIG,
            clock=self.clock,
        )
        self.record = RecordWebPresenceUC(self.web, verdicts, self.people, CONFIG, clock=self.clock)
        self.leave = LeaveWebPresenceUC(self.web)


def tab(session: str = "tab-0001", activity: Activity = Activity.viewing, doc: str | None = None) -> WebSignal:
    return WebSignal(session, activity, doc)


async def test__record__members_see_each_other_with_role_place_and_their_own_icon_marked() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor})
    await s.record.execute(actor("boris", "Борис Иванов"), PROJECT, tab("tab-boris", Activity.editing, "zayavka"))

    found = await s.record.execute(
        actor("anna", "Анна Петрова"), PROJECT, tab("tab-anna", Activity.reviewing, "zayavka")
    )

    assert [(p.name, p.me, p.role, p.activity, p.doc_id) for p in found.people] == [
        ("Анна Петрова", True, Role.owner, Activity.reviewing, "zayavka"),
        ("Борис Иванов", False, Role.editor, Activity.editing, "zayavka"),
    ]
    assert found.total == 2
    assert (found.interval_s, found.online_window_s) == (CONFIG.interval_s, CONFIG.online_window_s)
    assert [p.initials for p in found.people] == ["АП", "БИ"]


async def test__record__colour_of_the_avatar_is_the_colour_of_the_cursor() -> None:
    s = Stand({"anna": Role.owner})

    found = await s.record.execute(actor("anna", "Анна"), PROJECT, tab())

    assert found.people[0].color == person_color("anna")
    assert found.people[0].color == CollabIdentity(key="anna", name="Анна", can_write=True).color


async def test__record__two_tabs_of_one_person_are_one_avatar_with_the_freshest_place() -> None:
    s = Stand({"anna": Role.owner})
    anna = actor("anna", "Анна")
    await s.record.execute(anna, PROJECT, tab("tab-0001", Activity.viewing, "a"))
    s.clock.advance(seconds=20)

    found = await s.record.execute(anna, PROJECT, tab("tab-0002", Activity.editing, "b"))

    (person,) = found.people
    assert (person.activity, person.doc_id, person.channels) == (Activity.editing, "b", (Channel.web,))
    assert s.web.size() == 2


async def test__record__reader_and_reviewer_cannot_claim_to_edit() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.reader, "carol": Role.reviewer})
    await s.record.execute(actor("boris", "Борис"), PROJECT, tab("tab-boris", Activity.editing, "a"))
    await s.record.execute(actor("carol", "Карина"), PROJECT, tab("tab-carol", Activity.editing, "a"))

    found = await s.record.execute(actor("anna", "Анна"), PROJECT, tab("tab-anna", Activity.editing, "a"))

    assert {p.name: p.activity for p in found.people} == {
        "Анна": Activity.editing,
        "Борис": Activity.viewing,
        "Карина": Activity.viewing,
    }


async def test__record__a_stranger_and_a_guest_are_not_recorded_and_see_nobody() -> None:
    s = Stand({"anna": Role.owner})
    await s.record.execute(actor("anna", "Анна"), PROJECT, tab("tab-anna"))

    stranger = await s.record.execute(actor("zoe", "Зоя"), PROJECT, tab("tab-zoe"))
    guest = await s.record.execute(Actor.guest("gs_abc", "Гость"), PROJECT, tab("tab-gst1"))

    assert (stranger.people, guest.people) == ((), ())
    assert s.web.size() == 1


async def test__record__a_person_who_lost_access_disappears_after_the_check_expires_and_not_before() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor})
    await s.record.execute(actor("boris", "Борис"), PROJECT, tab("tab-boris"))
    del s.members["boris"]

    cached = await s.people.execute(actor("anna"), PROJECT)
    s.mono.now += 21
    later = await s.people.execute(actor("anna"), PROJECT)

    assert [p.user_id for p in cached.people] == ["boris"]
    assert later.people == ()


async def test__people__person_leaves_when_the_window_passes() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor})
    await s.record.execute(actor("boris", "Борис"), PROJECT, tab("tab-boris"))
    s.clock.advance(seconds=CONFIG.online_window_s + 1)

    found = await s.people.execute(actor("anna"), PROJECT)

    assert found.people == ()


async def test__leave__removes_the_tab_at_once_and_a_stranger_cannot_remove_it() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor})
    await s.record.execute(actor("boris", "Борис"), PROJECT, tab("tab-boris"))

    s.leave.execute(actor("anna"), PROJECT, "tab-boris")
    still = await s.people.execute(actor("anna"), PROJECT)
    s.leave.execute(actor("boris"), PROJECT, "tab-boris")
    gone = await s.people.execute(actor("anna"), PROJECT)

    assert [p.user_id for p in still.people] == ["boris"]
    assert gone.people == ()


async def test__people__local_studio_shows_as_working_locally_and_merges_with_the_web_tab() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor, "carol": Role.reader})
    s.devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=s.clock.now)
    s.devices.rows[("carol", "c" * 32)] = stored("carol", report("c" * 32), seen=s.clock.now)
    await s.record.execute(actor("carol", "Карина"), PROJECT, tab("tab-carol", Activity.viewing, "a"))

    found = await s.people.execute(actor("anna"), PROJECT)

    by_name = {p.name: p for p in found.people}
    assert by_name["Борис Иванов"].activity is Activity.local
    assert by_name["Борис Иванов"].channels == (Channel.studio,)
    assert by_name["Борис Иванов"].doc_id is None
    assert by_name["Карина"].channels == (Channel.web, Channel.studio)
    assert by_name["Карина"].activity is Activity.viewing


async def test__people__studio_details_of_the_machine_never_reach_the_list() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor})
    s.devices.rows[("boris", "b" * 32)] = stored(
        "boris", report("b" * 32, name="Секретный ноутбук Бориса", runner_id="r2"), seen=s.clock.now
    )

    found = await s.people.execute(actor("anna"), PROJECT)

    assert "Секретный" not in repr(found)
    assert "b" * 32 not in repr(found)


async def test__people__offline_studio_is_not_listed() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor})
    s.devices.rows[("boris", "b" * 32)] = stored("boris", report("b" * 32), seen=s.clock.now)
    s.clock.advance(minutes=10)

    assert (await s.people.execute(actor("anna"), PROJECT)).people == ()


async def test__people__the_list_is_capped_but_the_total_stays_honest() -> None:
    members = {f"u{n:03d}": Role.editor for n in range(60)}
    s = Stand({"anna": Role.owner, **members})
    for user_id in members:
        await s.record.execute(actor(user_id, user_id), PROJECT, tab(f"tab-{user_id}"))

    found = await s.people.execute(actor("anna"), PROJECT)

    assert (len(found.people), found.total) == (50, 60)


async def test__people__own_icon_goes_first_then_by_name() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor, "carol": Role.editor})
    for who, name in (("carol", "Карина"), ("boris", "Борис"), ("anna", "Яна")):
        await s.record.execute(actor(who, name), PROJECT, tab(f"tab-{who}"))

    found = await s.people.execute(actor("anna"), PROJECT)

    assert [p.name for p in found.people] == ["Яна", "Борис", "Карина"]


@pytest.mark.parametrize("activity", [Activity.viewing, Activity.building, Activity.browsing])
async def test__record__the_signal_never_touches_the_device_table(activity: Activity) -> None:
    s = Stand({"anna": Role.owner})

    await s.record.execute(actor("anna"), PROJECT, tab(activity=activity))

    assert s.devices.writes == 0


async def test__overview__people_only_on_request_and_only_with_the_right_to_read_sources() -> None:
    s = Stand({"anna": Role.owner, "boris": Role.editor, "gleb": Role.reader})
    await s.record.execute(actor("boris", "Борис"), PROJECT, tab("tab-boris", Activity.editing, "a"))
    members = s.members
    inner = ProjectStudiosUC(
        s.devices,  # type: ignore[arg-type]
        builder(s.clock),
        MemoryAcl(members),  # type: ignore[arg-type]
        MemoryUsers(user("anna", "Анна"), user("boris", "Борис")),  # type: ignore[arg-type]
        CONFIG,
    )
    full = DevicesOverviewUC(
        s.devices,  # type: ignore[arg-type]
        builder(s.clock),
        inner,
        MemoryAcl(members),  # type: ignore[arg-type]
        CONFIG,
        s.people,
    )
    no_sources = DevicesOverviewUC(
        s.devices,  # type: ignore[arg-type]
        builder(s.clock),
        inner,
        MemoryAcl(members, show_sources=False),  # type: ignore[arg-type]
        CONFIG,
        s.people,
    )

    asked = await full.execute(actor("anna"), "a" * 32, PROJECT, with_people=True)
    not_asked = await full.execute(actor("anna"), "a" * 32, PROJECT)
    reader = await no_sources.execute(actor("gleb"), "g" * 32, PROJECT, with_people=True)

    assert asked.people is not None
    assert [(p.name, p.activity, p.doc_id) for p in asked.people.people] == [("Борис", Activity.editing, "a")]
    assert not_asked.people is None
    assert reader.people is None
