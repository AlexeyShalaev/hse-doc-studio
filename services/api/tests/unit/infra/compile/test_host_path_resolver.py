from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.compile.host_path_resolver import (
    HostPathResolver,
    PathNotInContainerMountError,
)


@pytest.mark.unit
def test__to_host__no_mounts__returns_path_with_forward_slashes() -> None:
    resolver = HostPathResolver()

    assert resolver.to_host(Path("C:\\Users\\me\\hse\\vkr")) == "C:/Users/me/hse/vkr"


@pytest.mark.unit
def test__to_host__path_inside_projects_mount__swaps_prefix() -> None:
    resolver = HostPathResolver.from_mounts([("/projects", "D:/study")])

    assert resolver.to_host(Path("/projects/vkr-ru")) == "D:/study/vkr-ru"


@pytest.mark.unit
def test__to_host__path_is_the_mount_root__returns_host_root() -> None:
    resolver = HostPathResolver.from_mounts([("/projects", "D:/study")])

    assert resolver.to_host(Path("/projects")) == "D:/study"


@pytest.mark.unit
def test__to_host__project_inside_data_dir__uses_data_dir_mount() -> None:
    # Дефолтная топология README: отдельного маунта проектов нет, проект живёт в DATA_DIR.
    resolver = HostPathResolver.from_mounts([("/data", "C:/hse-studio-data")])

    assert resolver.to_host(Path("/data/projects/vkr")) == "C:/hse-studio-data/projects/vkr"


@pytest.mark.unit
def test__to_host__both_mounts_configured__prefers_the_projects_mount() -> None:
    resolver = HostPathResolver.from_mounts([("/projects", "D:/study"), ("/data", "C:/hse-studio-data")])

    assert resolver.to_host(Path("/projects/vkr")) == "D:/study/vkr"
    assert resolver.to_host(Path("/data/projects/vkr")) == "C:/hse-studio-data/projects/vkr"


@pytest.mark.unit
def test__to_host__path_outside_every_mount__raises() -> None:
    resolver = HostPathResolver.from_mounts([("/projects", "D:/study")])

    with pytest.raises(PathNotInContainerMountError):
        resolver.to_host(Path("/somewhere/else"))


@pytest.mark.unit
def test__to_host__mount_with_trailing_slash__still_matches() -> None:
    resolver = HostPathResolver.from_mounts([("/projects/", "D:/study/")])

    assert resolver.to_host(Path("/projects/vkr")) == "D:/study/vkr"
