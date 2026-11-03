"""Устройство локальной Студии: стабильный id, имя по умолчанию и имя, заданное человеком."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hse_doc_studio.core.devices.entities import DEVICE_ID_RE
from hse_doc_studio.core.devices.local import GENERIC_DEVICE_NAME
from hse_doc_studio.infra.devices.identity_store import JsonDeviceIdentity, default_device_name


@pytest.mark.parametrize(
    ("configured", "hostname", "expected"),
    [
        (None, "MacBook-Air-Alex.local", "MacBook-Air-Alex"),
        (None, "ALEX-PC", "ALEX-PC"),
        ("Рабочий ноутбук", "whatever", "Рабочий ноутбук"),
        (None, "6e8ef7c6e09c", GENERIC_DEVICE_NAME),
        ("", "6e8ef7c6e09c", GENERIC_DEVICE_NAME),
        ("/Users/alex/work", "6e8ef7c6e09c", GENERIC_DEVICE_NAME),
        (None, "a" * 64, GENERIC_DEVICE_NAME),
    ],
)
def test__default_device_name__machine_name_or_generic_for_container_ids(
    configured: str | None, hostname: str, expected: str
) -> None:
    assert default_device_name(configured, lambda: hostname) == expected


async def test__get__creates_stable_id_once(tmp_path: Path) -> None:
    store = JsonDeviceIdentity(tmp_path, configured_name=None, hostname=lambda: "host-1")

    first = await store.get()
    second = await JsonDeviceIdentity(tmp_path, configured_name=None, hostname=lambda: "host-1").get()

    assert DEVICE_ID_RE.fullmatch(first.device_id)
    assert second.device_id == first.device_id
    assert (first.name, first.custom) == ("host-1", False)


async def test__set_name__custom_name_survives_restart_and_empty_resets(tmp_path: Path) -> None:
    store = JsonDeviceIdentity(tmp_path, configured_name=None, hostname=lambda: "host-1")
    before = await store.get()

    renamed = await store.set_name("  Ноутбук  Алексея ")
    again = await JsonDeviceIdentity(tmp_path, configured_name=None, hostname=lambda: "host-1").get()
    reset = await store.set_name("")

    assert renamed.name == "Ноутбук Алексея"
    assert renamed.custom is True
    assert again.name == "Ноутбук Алексея"
    assert renamed.device_id == before.device_id == reset.device_id
    assert (reset.name, reset.custom) == ("host-1", False)


async def test__set_name__path_like_name_is_not_stored(tmp_path: Path) -> None:
    store = JsonDeviceIdentity(tmp_path, configured_name=None, hostname=lambda: "host-1")

    shown = await store.set_name("/Users/alex/secret")

    assert shown.custom is False
    assert "secret" not in (tmp_path / "device.json").read_text(encoding="utf-8")


async def test__get__broken_file_gets_a_new_identity_instead_of_crashing(tmp_path: Path) -> None:
    (tmp_path / "device.json").write_text("{not json", encoding="utf-8")

    found = await JsonDeviceIdentity(tmp_path, configured_name=None, hostname=lambda: "h").get()

    assert DEVICE_ID_RE.fullmatch(found.device_id)
    assert json.loads((tmp_path / "device.json").read_text(encoding="utf-8"))["device_id"] == found.device_id
