"""Сведения о хосте на сервере видит только администратор установки."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.host_details import hides_host_details
from hse_doc_studio.api.routers.v1.system import SystemInfoResponse, hide_host_details
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.mode import StudioMode


@pytest.fixture(autouse=True)
def _reset_actor() -> Iterator[None]:
    yield
    set_current_actor(None)


def test__hides_host_details__local_mode__never(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.local)
    set_current_actor(Actor.local())

    assert hides_host_details() is False


def test__hides_host_details__server__plain_user_hidden_admin_sees(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.server)

    set_current_actor(Actor.user("u1"))
    assert hides_host_details() is True
    set_current_actor(Actor.user("a1", is_instance_admin=True))
    assert hides_host_details() is False


def test__hide_host_details__keeps_version_and_drops_host_fields() -> None:
    info = SystemInfoResponse(
        version="1.2.3",
        mode="server",
        built="",
        deployment_mode="all-in-one",
        os="linux",
        os_version="#1 SMP Fri May",
        python_version="3.13.1",
        image_ref="ghcr.io/x/y:1.2.3",
        source_url="u",
        github_repo="r",
        license="MIT",
        docker="running",
        can_self_update=True,
        data_dir="/data",
        latest_version="1.2.3",
        update_available=False,
        update_checked_at=None,
        latest_release_date="",
        latest_release_notes=[],
        update_feed_enabled=True,
    )

    hidden = hide_host_details(info)

    assert hidden.version == "1.2.3"
    assert (hidden.os_version, hidden.python_version, hidden.data_dir) == ("", "", "")
    assert hidden.image_ref is None
    assert hidden.can_self_update is False
