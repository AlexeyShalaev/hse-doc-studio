"""Папки хоста поверх каталогов образа при самообновлении: что переносим, что снимаем, что пишем в журнал."""

from __future__ import annotations

import json
from typing import Any

import pytest
from hse_doc_studio.infra.update import updater
from hse_doc_studio.infra.update.updater import (
    build_run_command,
    drops_image_overlays,
    image_overlays,
    is_local_build,
)

_DEV_REF = "hse-doc-studio:dev"
_NEW_REF = "ghcr.io/alexeyshalaev/hse-doc-studio:0.16.0"
_OLD_PUBLISHED_REF = "ghcr.io/alexeyshalaev/hse-doc-studio:0.15.0"
_CHECKOUT_PACKS = "/Users/anna/hse-doc-studio/packs"
_HOST_DATA = "/Users/anna/hse-doc-studio/deploy/all-in-one/data"


def _container(image_ref: str) -> dict[str, Any]:
    """Контейнер, поднятый `compose.build.yml`: данные, сокет и паки checkout поверх /app/packs."""
    return {
        "Name": "/hse-doc-studio-hse-doc-studio-1",
        "Image": "sha256:oldoldoldold",
        "Config": {"Image": image_ref, "Env": ["HSE_STUDIO__DATA_DIR=/data"], "Labels": {}},
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}},
        "State": {"Health": {"Status": "healthy"}},
        "Mounts": [
            {"Type": "bind", "Source": _HOST_DATA, "Destination": "/data", "RW": True},
            {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True},
            {"Type": "bind", "Source": _CHECKOUT_PACKS, "Destination": "/app/packs", "RW": False},
        ],
    }


def _volumes(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, part in enumerate(cmd) if part == "-v"]


class _Docker:
    def __init__(self, container: dict[str, Any]) -> None:
        self.calls: list[list[str]] = []
        self._objects = {
            "hse-doc-studio-hse-doc-studio-1": container,
            "sha256:oldoldoldold": {"Config": {"Env": []}},
            _NEW_REF: {"Config": {"Env": []}},
        }

    def __call__(self, args: list[str], timeout: float = 0.0) -> tuple[int, str, str]:
        self.calls.append(list(args))
        if args[0] == "inspect":
            found = self._objects.get(args[1])
            return (0, json.dumps([found]), "") if found is not None else (1, "", "no such object")
        return 0, "", ""

    @property
    def run_command(self) -> list[str]:
        return next(call for call in self.calls if call[0] == "run")


class _Log(updater._Log):
    def __init__(self) -> None:
        super().__init__(None)
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        self.lines.append(message)


def _update(monkeypatch: pytest.MonkeyPatch, image_ref: str) -> tuple[int, _Docker, _Log]:
    docker = _Docker(_container(image_ref))
    monkeypatch.setattr(updater, "_docker", docker)
    log = _Log()
    code = updater.run_update("hse-doc-studio-hse-doc-studio-1", _NEW_REF, log)
    return code, docker, log


@pytest.mark.unit
def test__image_overlays__only_bind_mounts_under_app() -> None:
    found = image_overlays(_container(_DEV_REF)["Mounts"])

    assert found == [{"destination": "/app/packs", "source": _CHECKOUT_PACKS}]


@pytest.mark.unit
def test__image_overlays__named_volume_under_app__is_not_an_overlay() -> None:
    mounts = [{"Type": "volume", "Name": "cache", "Destination": "/app/cache"}]

    assert image_overlays(mounts) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ref", "local"),
    [
        ("hse-doc-studio:dev", True),
        ("hse-doc-studio", True),
        ("ghcr.io/alexeyshalaev/hse-doc-studio:0.16.0", False),
        ("alexeyshalaev/hse-doc-studio:latest", False),
        ("localhost:5000/hse-doc-studio:dev", False),
        ("sha256:abcdef", False),
        (None, False),
    ],
)
def test__is_local_build(ref: str | None, local: bool) -> None:
    assert is_local_build(ref) is local


@pytest.mark.unit
def test__drops_image_overlays__dev_build_to_published__drops() -> None:
    assert drops_image_overlays(_DEV_REF, _NEW_REF)


@pytest.mark.unit
def test__drops_image_overlays__published_to_published__keeps() -> None:
    assert not drops_image_overlays(_OLD_PUBLISHED_REF, _NEW_REF)


@pytest.mark.unit
def test__drops_image_overlays__reconfigure_without_new_image__keeps() -> None:
    assert not drops_image_overlays(_DEV_REF, None)


@pytest.mark.unit
def test__build_run_command__drop_mounts__skips_only_that_destination() -> None:
    cmd = build_run_command(_container(_DEV_REF), {"Config": {"Env": []}}, _NEW_REF, drop_mounts=("/app/packs",))

    assert _volumes(cmd) == [f"{_HOST_DATA}:/data", "/var/run/docker.sock:/var/run/docker.sock"]


@pytest.mark.unit
def test__run_update__dev_build_to_published__packs_mount_not_carried_over(monkeypatch: pytest.MonkeyPatch) -> None:
    code, docker, _log = _update(monkeypatch, _DEV_REF)

    assert code == 0
    volumes = _volumes(docker.run_command)
    assert all(not v.endswith(":/app/packs:ro") for v in volumes)
    # Пользовательские данные и сокет остаются на месте.
    assert f"{_HOST_DATA}:/data" in volumes
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes


@pytest.mark.unit
def test__run_update__dev_build_to_published__logs_the_dropped_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    _code, _docker, log = _update(monkeypatch, _DEV_REF)

    assert any(_CHECKOUT_PACKS in line and "not carried over" in line for line in log.lines)


@pytest.mark.unit
def test__run_update__published_to_published__keeps_the_mount_and_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    code, docker, log = _update(monkeypatch, _OLD_PUBLISHED_REF)

    assert code == 0
    assert f"{_CHECKOUT_PACKS}:/app/packs:ro" in _volumes(docker.run_command)
    assert any(line.startswith("WARNING") and "/app/packs" in line for line in log.lines)


@pytest.mark.unit
def test__rollback__restores_the_dropped_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    # Новый контейнер не поднялся: откат возвращает прежнюю конфигурацию вместе с привязкой паков.
    container = _container(_DEV_REF)
    log = _Log()
    rollback_cmd: list[str] = []

    def _recreate(_name: str, cmd: list[str], _log: object) -> bool:
        rollback_cmd[:] = cmd
        return True

    monkeypatch.setattr(updater, "_recreate", _recreate)
    monkeypatch.setattr(updater, "_wait_healthy", lambda _name, _log: True)

    assert updater._rollback(container, "sha256:oldoldoldold", {"Config": {"Env": []}}, log) == 4
    assert f"{_CHECKOUT_PACKS}:/app/packs:ro" in _volumes(rollback_cmd)
