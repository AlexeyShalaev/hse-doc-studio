"""Скрипт установки раннера: шаблон без секретов, POSIX sh, режим plan ничего не меняет."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from hse_doc_studio.api.runner_commands import (
    install_script_url,
    registration_docker_command,
    registration_script_command,
)
from hse_doc_studio.api.runner_install import IMAGE_PLACEHOLDER, render_install_script

pytestmark = pytest.mark.unit

SECRET = "hsrt_supersecret"
IMAGE = "registry.example/hds:9.9.9"


def _script(tmp_path: Path) -> Path:
    path = tmp_path / "install.sh"
    path.write_text(render_install_script(IMAGE), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _run(
    tmp_path: Path, *args: str, uname: str, extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    (shim / "uname").write_text(f"#!/bin/sh\necho {uname}\n")
    (shim / "uname").chmod(0o755)
    env = {
        "PATH": f"{shim}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path / "home"),
        "HSE_RUNNER__API_URL": "https://studio.example.org",
        "HSE_RUNNER__TOKEN": SECRET,
        **(extra or {}),
    }
    return subprocess.run(  # noqa: S603
        ["/bin/sh", str(_script(tmp_path)), *args], env=env, capture_output=True, text=True, timeout=30, check=False
    )


def test__render__has_no_secret_and_no_placeholder() -> None:
    text = render_install_script(IMAGE)

    assert IMAGE in text
    assert IMAGE_PLACEHOLDER not in text
    assert "hsrt_" not in text
    assert text.startswith("#!/bin/sh\n")


def test__render__is_the_same_for_everyone() -> None:
    assert render_install_script(IMAGE) == render_install_script(IMAGE)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test__script__passes_shellcheck(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603
        ["shellcheck", "-s", "sh", str(_script(tmp_path))], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("uname", ["Linux", "Darwin"])
def test__plan__prints_actions_masks_token_and_writes_nothing(tmp_path: Path, uname: str) -> None:
    result = _run(tmp_path, "plan", uname=uname)

    assert result.returncode == 0, result.stderr
    assert IMAGE in result.stdout
    assert "would run:" in result.stdout
    assert "  studio  : https://studio.example.org" in result.stdout.splitlines()
    assert SECRET not in result.stdout + result.stderr
    assert "TOKEN=***" in result.stdout
    assert not (tmp_path / "home").exists()


def test__plan__linux_writes_systemd_unit_in_output(tmp_path: Path) -> None:
    result = _run(tmp_path, "plan", uname="Linux")

    assert "/etc/systemd/system/hse-runner.service" in result.stdout
    assert "Restart=always" in result.stdout
    assert "--env-file /etc/hse-runner/hse-runner.env" in result.stdout


def test__plan__macos_writes_launchd_plist_in_output(tmp_path: Path) -> None:
    result = _run(tmp_path, "plan", uname="Darwin")

    assert "ru.hse-doc-studio.hse-runner.plist" in result.stdout
    assert "<key>KeepAlive</key>" in result.stdout
    assert "gui/" in result.stdout


def test__plan__custom_service_name_changes_every_path(tmp_path: Path) -> None:
    result = _run(tmp_path, "plan", uname="Linux", extra={"HSE_RUNNER_SERVICE": "hds-two"})

    assert "/etc/systemd/system/hds-two.service" in result.stdout
    assert "/etc/hse-runner/hds-two.env" in result.stdout


def test__install__without_studio_address_fails_with_clear_message(tmp_path: Path) -> None:
    result = _run(tmp_path, "plan", uname="Linux", extra={"HSE_RUNNER__API_URL": ""})

    assert result.returncode != 0
    assert "HSE_RUNNER__API_URL" in result.stderr


def test__unknown_action__prints_usage(tmp_path: Path) -> None:
    result = _run(tmp_path, "frobnicate", uname="Linux")

    assert result.returncode != 0
    assert "usage:" in result.stderr


def test__unsupported_os__fails(tmp_path: Path) -> None:
    result = _run(tmp_path, "plan", uname="FreeBSD")

    assert result.returncode != 0
    assert "unsupported OS" in result.stderr


def test__uninstall_plan__keeps_data_without_purge(tmp_path: Path) -> None:
    kept = _run(tmp_path, "uninstall", uname="Linux", extra={"HSE_RUNNER_DRY_RUN": "1"})
    purged = _run(tmp_path, "uninstall", "--purge", uname="Linux", extra={"HSE_RUNNER_DRY_RUN": "1"})

    assert kept.returncode == 0, kept.stderr
    assert "kept the data directory" in kept.stdout
    assert "would run: rm -rf" in purged.stdout


def test__commands__keep_secret_out_of_script_and_url() -> None:
    base = "https://studio.example.org"

    linux = registration_script_command(base, SECRET)
    mac = registration_script_command(base, SECRET, macos=True)
    docker = registration_docker_command(base, SECRET, env_name="HSE_RUNNER__RUNNER_TOKEN")

    assert install_script_url(base) in linux
    assert SECRET not in install_script_url(base)
    assert linux.split("|", 1)[0].strip().endswith("install.sh")
    assert " sudo env " in linux
    assert "sudo" not in mac
    assert f"-e HSE_RUNNER__RUNNER_TOKEN={SECRET}" in docker
