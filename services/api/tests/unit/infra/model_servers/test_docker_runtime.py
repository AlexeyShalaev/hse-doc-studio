"""Docker-развёртыватель: аргументы без секретов, env-файл удаляется, откат на процессор."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.model_servers import ContainerRunError, Engine, build_container_spec
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.model_servers import docker_runtime
from hse_doc_studio.infra.model_servers.docker_runtime import DockerContainerRuntime, run_args

SECRET = "S3CR3T-TOKEN"


def _spec(**kw: object):  # type: ignore[no-untyped-def]
    return build_container_spec(Engine.vllm, server_id="ab12", model="Qwen/Qwen3-4B", hf_token=SECRET, gpu=True, **kw)


def test_run_args_have_no_secret_and_no_public_port() -> None:
    args = run_args(_spec(), None, "/tmp/x.env", gpu=True)  # noqa: S108
    assert SECRET not in " ".join(args)
    assert "--env-file" in args
    assert "127.0.0.1::8000" in args  # только loopback хоста, без сети
    assert args[args.index("--gpus") + 1] == "all"


def test_run_args_in_shared_network_publish_nothing() -> None:
    args = run_args(_spec(), "hse-studio-net", None, gpu=False)
    assert "-p" not in args
    assert args[args.index("--network") + 1] == "hse-studio-net"


class _Docker:
    def __init__(self, results: list[tuple[int | None, str, str]]) -> None:
        self.results = results
        self.calls: list[list[str]] = []
        self.env_files: list[str] = []

    async def __call__(self, args: list[str], timeout: float = 0) -> tuple[int | None, str, str]:
        self.calls.append(args)
        if "--env-file" in args:
            path = args[args.index("--env-file") + 1]
            self.env_files.append(path)
            assert SECRET in Path(path).read_text()
            assert oct(Path(path).stat().st_mode & 0o777) == "0o600"
        return self.results.pop(0)


async def test_env_file_is_removed_and_secret_not_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Docker([(1, "", f"boom {SECRET}")])
    monkeypatch.setattr(docker_runtime, "run_docker", fake)
    with pytest.raises(ContainerRunError) as err:
        await DockerContainerRuntime(SiblingNetwork.disabled()).run(_spec())
    assert SECRET not in str(err.value)
    assert not Path(fake.env_files[0]).exists()


async def test_gpu_failure_falls_back_to_cpu_for_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Docker([(1, "", "no runtime"), (0, "", ""), (0, "cid\n", "")])
    monkeypatch.setattr(docker_runtime, "run_docker", fake)
    spec = build_container_spec(Engine.ollama, server_id="ab12", model="qwen3:4b", gpu=True)
    assert await DockerContainerRuntime(SiblingNetwork.disabled()).run(spec) == "cid"
    assert "--gpus" in fake.calls[0]
    assert fake.calls[1][:2] == ["rm", "-f"]
    assert "--gpus" not in fake.calls[2]


async def test_gpu_failure_is_final_for_vllm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Docker([(1, "", "no runtime")])
    monkeypatch.setattr(docker_runtime, "run_docker", fake)
    with pytest.raises(ContainerRunError):
        await DockerContainerRuntime(SiblingNetwork.disabled()).run(_spec())
    assert len(fake.calls) == 1
