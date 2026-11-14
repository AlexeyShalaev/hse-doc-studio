"""Обновление раннера «Docker рядом»: после успеха снимаются теги образа старше предыдущей версии (storage-cleanup.md,
14.2, A14)."""

from __future__ import annotations

import json

import pytest
from hse_doc_studio.infra.runner_install import docker_host
from hse_doc_studio.infra.runner_install.docker_host import DockerLocalHost
from hse_doc_studio.infra.runner_install.kube_host import KubeLocalHost

pytestmark = pytest.mark.unit

_REPO = "registry.example/hds"


class _Docker:
    """`image ls` отдаёт теги, `image rm` без `--force` отказывает для занятых."""

    def __init__(self, tags: list[str], in_use: set[str] | None = None) -> None:
        self.tags = tags
        self.in_use = in_use or set()
        self.calls: list[list[str]] = []

    async def __call__(self, args: list[str], timeout: float = 30.0) -> tuple[int | None, str, str]:
        self.calls.append(args)
        if args[:2] == ["image", "ls"]:
            rows = [json.dumps({"Repository": _REPO, "Tag": tag}) for tag in self.tags]
            rows.append(json.dumps({"Repository": "other/repo", "Tag": "0.0.1"}))
            return 0, "\n".join(rows) + "\n", ""
        if args[:2] == ["image", "rm"]:
            if "--force" in args or "-f" in args:
                raise AssertionError("never forced")
            ref = args[-1]
            if ref in self.in_use:
                return 1, "", "image is being used by stopped container"
            return 0, "", ""
        return 0, "", ""


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> _Docker:
    fake = _Docker(["0.20.0", "0.21.0", "0.22.0", "0.23.0", "latest", "rollback-prev"], {f"{_REPO}:0.20.0"})
    monkeypatch.setattr(docker_host, "run_docker", fake)
    return fake


async def test__docker__removes_tags_below_the_previous_version(docker: _Docker) -> None:
    removed = await DockerLocalHost().prune_old_images(f"{_REPO}:0.23.0", f"{_REPO}:0.22.0")

    # 0.20.0 занят (Docker отказал), 0.22.0 и 0.23.0 откат и текущая, остальное не номер версии.
    assert removed == [f"{_REPO}:0.21.0"]
    assert ["image", "rm", f"{_REPO}:0.20.0"] in docker.calls


@pytest.mark.parametrize(
    ("image", "previous"),
    [
        (f"{_REPO}:0.23.0", f"{_REPO}:latest"),
        (f"{_REPO}:0.23.0", "sha256:abc"),
        (f"{_REPO}:0.23.0", "elsewhere/hds:0.22.0"),
        (f"{_REPO}:latest", f"{_REPO}:0.22.0"),
    ],
)
async def test__docker__unknown_previous_or_other_repo__nothing(docker: _Docker, image: str, previous: str) -> None:
    assert await DockerLocalHost().prune_old_images(image, previous) == []
    assert not [call for call in docker.calls if call[:2] == ["image", "rm"]]


async def test__kube__never_touches_node_images() -> None:
    host = KubeLocalHost.__new__(KubeLocalHost)
    assert await host.prune_old_images(f"{_REPO}:0.23.0", f"{_REPO}:0.22.0") == []
