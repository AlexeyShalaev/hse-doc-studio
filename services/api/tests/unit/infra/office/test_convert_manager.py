from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager


def _make_manager(*, fonts_dir: Path | None = None) -> OfficeConvertManager:
    return OfficeConvertManager(
        image="gotenberg/gotenberg:8",
        container_name="test-office-convert",
        container_port=3000,
        health_path="/health",
        convert_timeout_s=1.0,
        health_timeout_s=1.0,
        startup_timeout_s=1.0,
        idle_timeout_s=1.0,
        fonts_dir=fonts_dir,
        fonts_host_dir=None,
        client=MagicMock(),
        siblings=SiblingNetwork.disabled(),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("runtime_image", "expected_checked_image"),
    [
        pytest.param("gotenberg/gotenberg:9", "gotenberg/gotenberg:9", id="runtime_override"),
        pytest.param(None, "gotenberg/gotenberg:8", id="deploy_default"),
    ],
)
async def test__ensure_running__image_override__checks_effective_image(
    runtime_image: str | None, expected_checked_image: str
) -> None:
    manager = _make_manager()
    manager._docker_available = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager._image_present = AsyncMock(return_value=False)  # type: ignore[method-assign]

    result = await manager.ensure_running(runtime_image)

    assert result is None
    manager._image_present.assert_awaited_once_with(expected_checked_image)


@pytest.mark.unit
async def test__convert_to_pdf__passes_runtime_image_to_ensure_running(tmp_path: Path) -> None:
    manager = _make_manager()
    manager.ensure_running = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await manager.convert_to_pdf(tmp_path / "pres.pptx", image="gotenberg/gotenberg:9") is None
    manager.ensure_running.assert_awaited_once_with("gotenberg/gotenberg:9")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("expected_image", "removes_stale_container"),
    [
        pytest.param("gotenberg/gotenberg:9", True, id="stale_image_removed"),
        pytest.param("gotenberg/gotenberg:8", False, id="same_image_kept"),
        pytest.param(None, False, id="no_expected_image_not_compared"),
    ],
)
async def test__inspect__stale_recreate_compares_with_expected_image(
    expected_image: str | None, removes_stale_container: bool
) -> None:
    manager = _make_manager()
    calls: list[list[str]] = []

    async def fake_run(args: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(args)
        if args[0] == "ps":
            return 0, "running|gotenberg/gotenberg:8", ""
        return 0, "", ""

    manager._run_docker_raw = fake_run  # type: ignore[method-assign]

    state = await manager._inspect(expected_image)

    assert state == ("absent" if removes_stale_container else "running")
    assert (["rm", "-f", "test-office-convert"] in calls) is removes_stale_container


@pytest.mark.unit
@pytest.mark.parametrize(
    ("docker_raw_result", "expected"),
    [
        pytest.param((0, "exited|Exited (0) 2 hours ago", ""), (True, False, "Exited (0) 2 hours ago"), id="exited"),
        pytest.param((0, "", ""), (False, False, None), id="empty_output"),
        pytest.param((1, "", "boom"), (False, False, None), id="docker_error"),
    ],
)
async def test__inspect_state__pure_read_for_status_api(
    docker_raw_result: tuple[int, str, str], expected: tuple[bool, bool, str | None]
) -> None:
    manager = _make_manager()
    manager._run_docker_raw = AsyncMock(return_value=docker_raw_result)  # type: ignore[method-assign]

    result = await manager.inspect_state()

    assert result == expected
