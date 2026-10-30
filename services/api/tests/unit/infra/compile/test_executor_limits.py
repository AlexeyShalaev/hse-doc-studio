"""Флаги изоляции контейнера сборки: у раннера включены, у встроенного раннера argv прежний."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.docker.cli import configure_docker_binary

from tests.unit.infra.runner.fake_docker import install_fake_docker, recorded_calls

ISOLATION_FLAGS = ("--network", "--read-only", "--tmpfs", "--cpus", "--memory", "--pids-limit", "--security-opt")


@pytest.fixture
def docker_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    configure_docker_binary(str(install_fake_docker(tmp_path)))
    yield log
    configure_docker_binary(None)


async def _compile(limits: ExecutorLimits | None, tmp_path: Path) -> list[str]:
    project = tmp_path / "project"
    (project / "tz").mkdir(parents=True)
    (project / "tz" / "main.tex").write_text("x")
    executor = DockerCompileExecutor(HostPathResolver(), limits=limits)
    lines = await executor.run(project, "tz/main.tex", "xelatex", 3, "tz", uuid4())
    return [line async for line in lines]


def test__docker_args__hardened_profile__lists_every_flag() -> None:
    args = ExecutorLimits(cpus=1.5, memory="2g", pids_limit=100, tmpfs_tmp="64m").docker_args()

    assert args == [
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,size=64m",
        "--cpus",
        "1.5",
        "--memory",
        "2g",
        "--pids-limit",
        "100",
        "--security-opt",
        "no-new-privileges",
    ]


def test__docker_args__optional_limits_off__only_switches_remain() -> None:
    limits = ExecutorLimits(cpus=None, memory=None, pids_limit=None, read_only_rootfs=False)

    assert limits.docker_args() == ["--network", "none", "--security-opt", "no-new-privileges"]


async def test__run__embedded_profile__argv_has_no_isolation_flags(tmp_path: Path, docker_log: Path) -> None:
    await _compile(None, tmp_path)

    runs = [call for call in recorded_calls(docker_log) if call[:1] == ["run"]]
    assert len(runs) == 2
    for call in runs:
        assert not set(ISOLATION_FLAGS) & set(call)


async def test__run__runner_profile__both_containers_are_isolated(tmp_path: Path, docker_log: Path) -> None:
    lines = await _compile(ExecutorLimits(), tmp_path)

    runs = [call for call in recorded_calls(docker_log) if call[:1] == ["run"]]
    assert len(runs) == 2
    for call in runs:
        assert call[call.index("--network") + 1] == "none"
        assert "--read-only" in call
        assert "no-new-privileges" in call
        # флаги стоят до образа и до команды внутри контейнера
        assert call.index("--read-only") < call.index("-v")
    assert any("pdf written" in line for line in lines)
