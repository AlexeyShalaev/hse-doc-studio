"""Веб-сессии проектов в памяти: окно, выход вкладки и пределы памяти (docs/design/connected-devices.md, 15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.devices.people import (
    MAX_SESSIONS_PER_PROJECT,
    MAX_SESSIONS_PER_USER,
    MAX_SESSIONS_TOTAL,
    Activity,
    WebSignal,
)
from hse_doc_studio.infra.devices.web_registry import WebPresenceRegistry

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
PROJECT = UUID("11111111-1111-1111-1111-111111111111")
WINDOW = 180


def sig(session: str, activity: Activity = Activity.viewing, doc: str | None = None) -> WebSignal:
    return WebSignal(session.ljust(8, "x"), activity, doc)


def test__sessions__are_alive_inside_the_window_and_gone_after_it() -> None:
    registry = WebPresenceRegistry()
    registry.observe(PROJECT, "anna", "Анна", sig("tab1"), T0, WINDOW)

    assert len(registry.sessions(PROJECT, T0 + timedelta(seconds=WINDOW), WINDOW)) == 1
    assert registry.sessions(PROJECT, T0 + timedelta(seconds=WINDOW + 1), WINDOW) == []


def test__observe__same_tab_replaces_its_session_and_two_tabs_are_two_sessions() -> None:
    registry = WebPresenceRegistry()
    registry.observe(PROJECT, "anna", "Анна", sig("tab1", Activity.viewing), T0, WINDOW)
    registry.observe(PROJECT, "anna", "Анна", sig("tab1", Activity.editing, "main"), T0 + timedelta(seconds=5), WINDOW)
    registry.observe(PROJECT, "anna", "Анна", sig("tab2"), T0 + timedelta(seconds=6), WINDOW)

    sessions = registry.sessions(PROJECT, T0 + timedelta(seconds=10), WINDOW)

    assert sorted((s.session_id, s.activity.value) for s in sessions) == [
        ("tab1xxxx", "editing"),
        ("tab2xxxx", "viewing"),
    ]
    assert registry.size() == 2


def test__leave__removes_only_that_tab_and_only_for_that_person() -> None:
    registry = WebPresenceRegistry()
    registry.observe(PROJECT, "anna", "Анна", sig("tab1"), T0, WINDOW)
    registry.observe(PROJECT, "anna", "Анна", sig("tab2"), T0, WINDOW)
    registry.observe(PROJECT, "boris", "Борис", sig("tab1"), T0, WINDOW)

    registry.leave(PROJECT, "anna", sig("tab1").session_id)
    registry.leave(PROJECT, "carol", sig("tab2").session_id)

    left = {(s.user_id, s.session_id) for s in registry.sessions(PROJECT, T0, WINDOW)}
    assert left == {("anna", "tab2xxxx"), ("boris", "tab1xxxx")}
    assert registry.size() == 2


def test__observe__expired_sessions_are_dropped_from_memory_on_the_next_write() -> None:
    registry = WebPresenceRegistry()
    for n in range(10):
        registry.observe(PROJECT, f"u{n}", "Имя", sig("tab"), T0, WINDOW)

    registry.observe(PROJECT, "late", "Поздний", sig("tab"), T0 + timedelta(seconds=WINDOW + 1), WINDOW)

    assert registry.size() == 1


def test__observe__one_person_keeps_at_most_the_newest_tabs() -> None:
    registry = WebPresenceRegistry()
    for n in range(MAX_SESSIONS_PER_USER + 3):
        registry.observe(PROJECT, "anna", "Анна", sig(f"tab{n:02d}"), T0 + timedelta(seconds=n), WINDOW)

    kept = {s.session_id for s in registry.sessions(PROJECT, T0 + timedelta(seconds=30), WINDOW)}

    assert len(kept) == MAX_SESSIONS_PER_USER
    newest = f"tab{MAX_SESSIONS_PER_USER + 2:02d}".ljust(8, "x")
    assert ("tab00xxx" in kept, newest in kept) == (False, True)


def test__observe__a_project_never_holds_more_than_its_limit() -> None:
    registry = WebPresenceRegistry()
    for n in range(MAX_SESSIONS_PER_PROJECT + 20):
        registry.observe(PROJECT, f"u{n}", "Имя", sig("tab"), T0 + timedelta(milliseconds=n), WINDOW)

    assert registry.size() == MAX_SESSIONS_PER_PROJECT


def test__observe__the_replica_never_holds_more_than_the_total_limit() -> None:
    registry = WebPresenceRegistry()
    per_project = MAX_SESSIONS_PER_PROJECT
    projects = MAX_SESSIONS_TOTAL // per_project + 2
    for p in range(projects):
        pid = uuid4()
        for n in range(per_project):
            registry.observe(pid, f"u{n}", "Имя", sig("tab"), T0 + timedelta(milliseconds=p * per_project + n), WINDOW)

    assert registry.size() <= MAX_SESSIONS_TOTAL
