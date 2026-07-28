from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from pytest_lazy_fixtures import lf


def _executor(fonts_dir: Path | None, host_dir: str | None) -> DockerCompileExecutor:
    return DockerCompileExecutor(
        host_path_resolver=HostPathResolver(),
        fonts_dir=fonts_dir,
        fonts_host_dir=host_dir,
        fonts_mount_target="/usr/local/share/fonts/hse",
    )


@pytest.fixture
def missing_fonts_dir(tmp_path: Path) -> Path:
    return tmp_path / "nope"


@pytest.fixture
def empty_fonts_dir(tmp_path: Path) -> Path:
    empty = tmp_path / "fonts"
    empty.mkdir()
    return empty


@pytest.fixture
def fonts_dir_without_font_files(tmp_path: Path) -> Path:
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "readme.txt").write_text("x", encoding="utf-8")
    return fonts


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fonts_dir", "host_dir"),
    [
        pytest.param(None, None, id="unconfigured"),
        pytest.param(lf("missing_fonts_dir"), "/host/fonts", id="missing_dir"),
        pytest.param(lf("empty_fonts_dir"), "/host/fonts", id="empty_dir"),
        pytest.param(lf("fonts_dir_without_font_files"), "/host/fonts", id="no_font_files"),
    ],
)
def test__docker_compile_executor_fonts_mount_args__no_usable_fonts__returns_empty_list(
    fonts_dir: Path | None, host_dir: str | None
) -> None:
    assert _executor(fonts_dir, host_dir)._fonts_mount_args() == []


@pytest.mark.unit
def test__docker_compile_executor_fonts_mount_args__font_file_present__returns_ro_mount_arg(
    tmp_path: Path,
) -> None:
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "times.ttf").write_bytes(b"x")

    args = _executor(fonts, "/host/data/fonts")._fonts_mount_args()

    assert args == ["-v", "/host/data/fonts:/usr/local/share/fonts/hse:ro"]
