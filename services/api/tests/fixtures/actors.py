"""Акторы для тестов: подмена current_actor() и пара «владелец и посторонний»."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from hse_doc_studio.core.access.context import current_actor, set_current_actor
from hse_doc_studio.core.access.entities import Actor


@contextmanager
def as_actor(actor: Actor | None) -> Iterator[Actor | None]:
    """Выполнить блок от имени актора и вернуть прежнего, даже если блок упал."""
    previous = current_actor()
    set_current_actor(actor)
    try:
        yield actor
    finally:
        set_current_actor(previous)


@pytest.fixture(autouse=True)
def _reset_current_actor() -> Iterator[None]:
    """Тест не должен оставлять актора следующему."""
    previous = current_actor()
    yield
    set_current_actor(previous)


@pytest.fixture
def two_actors() -> tuple[Actor, Actor]:
    """Два разных пользователя для проверок изоляции данных."""
    return (
        Actor.user("user-a", name="Owner", email="owner@example.test"),
        Actor.user("user-b", name="Stranger", email="stranger@example.test"),
    )
