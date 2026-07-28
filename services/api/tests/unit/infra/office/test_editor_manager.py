from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from pytest_lazy_fixtures import lf


def _make_manager(tmp_path: Path, *, fonts_dir: Path | None = None) -> OfficeEditorManager:
    return OfficeEditorManager(
        image="onlyoffice/documentserver:latest",
        container_name="test-office-editor",
        container_port=80,
        health_path="/healthcheck",
        health_timeout_s=1.0,
        startup_timeout_s=1.0,
        idle_timeout_s=1.0,
        secret_path=tmp_path / "office-editor-jwt.secret",
        fonts_dir=fonts_dir,
        fonts_host_dir=None,
        client=MagicMock(),
        siblings=SiblingNetwork.disabled(),
    )


@pytest.mark.unit
def test__jwt_secret__created_once_and_persisted(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    secret = manager.jwt_secret

    assert secret
    assert (tmp_path / "office-editor-jwt.secret").read_text(encoding="utf-8").strip() == secret
    # Второй инстанс (рестарт бэкенда) читает ТОТ ЖЕ секрет — усыновлённый
    # контейнер продолжает валидировать старые токены.
    assert _make_manager(tmp_path).jwt_secret == secret


@pytest.mark.unit
async def test__reaper__does_not_stop_while_sessions_active(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._inspect = AsyncMock(return_value="running")  # type: ignore[method-assign]
    manager._run_docker_raw = AsyncMock(return_value=(0, "", ""))  # type: ignore[method-assign]
    manager._last_used = time.monotonic() - 10_000  # давно за idle_timeout
    manager.mark_active("key-1")
    manager._last_used = time.monotonic() - 10_000

    await manager._maybe_reap()

    manager._run_docker_raw.assert_not_awaited()  # живой редактор — не гасим

    manager.mark_closed("key-1")
    manager._last_used = time.monotonic() - 10_000
    await manager._maybe_reap()

    manager._run_docker_raw.assert_awaited()  # сессий нет — обычный idle-stop


@pytest.mark.unit
def test__touch__postpones_reap(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._last_used = time.monotonic() - 10_000

    manager.touch()

    assert manager._last_used is not None
    assert time.monotonic() - manager._last_used < 1.0


@pytest.fixture
def absent_fonts_dir(tmp_path: Path) -> Path:
    return tmp_path / "absent"


@pytest.fixture
def empty_fonts_dir(tmp_path: Path) -> Path:
    empty = tmp_path / "fonts-empty"
    empty.mkdir()
    return empty


@pytest.mark.unit
@pytest.mark.parametrize(
    "fonts_dir",
    [
        pytest.param(None, id="unconfigured"),
        pytest.param(lf("absent_fonts_dir"), id="missing_dir"),
        pytest.param(lf("empty_fonts_dir"), id="empty_dir"),
    ],
)
def test__fonts_mount__skipped_when_dir_missing_or_empty(tmp_path: Path, fonts_dir: Path | None) -> None:
    assert _make_manager(tmp_path, fonts_dir=fonts_dir)._fonts_mount_args() == []


@pytest.mark.unit
def test__fonts_mount__targets_ds_font_path(tmp_path: Path) -> None:
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "TNR.ttf").write_bytes(b"font")

    args = _make_manager(tmp_path, fonts_dir=fonts)._fonts_mount_args()

    assert args == ["-v", f"{fonts}:/usr/share/fonts/truetype/hse:ro"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("runtime_image", "expected_checked_image"),
    [
        pytest.param("onlyoffice/documentserver:9.0", "onlyoffice/documentserver:9.0", id="runtime_override"),
        pytest.param(None, "onlyoffice/documentserver:latest", id="deploy_default"),
    ],
)
async def test__ensure_running__image_override__checks_effective_image(
    tmp_path: Path, runtime_image: str | None, expected_checked_image: str
) -> None:
    manager = _make_manager(tmp_path)
    manager._docker_available = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager._image_present = AsyncMock(return_value=False)  # type: ignore[method-assign]

    result = await manager.ensure_running(runtime_image)

    assert result is None
    manager._image_present.assert_awaited_once_with(expected_checked_image)


@pytest.mark.unit
async def test__is_image_missing__uses_effective_image(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._docker_available = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager._image_present = AsyncMock(return_value=False)  # type: ignore[method-assign]

    assert await manager.is_image_missing("onlyoffice/documentserver:9.0") is True
    manager._image_present.assert_awaited_once_with("onlyoffice/documentserver:9.0")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("expected_image", "removes_stale_container"),
    [
        pytest.param("onlyoffice/documentserver:9.0", True, id="stale_image_removed"),
        pytest.param(None, False, id="no_expected_image_not_compared"),
    ],
)
async def test__inspect__stale_recreate_compares_with_expected_image(
    tmp_path: Path, expected_image: str | None, removes_stale_container: bool
) -> None:
    manager = _make_manager(tmp_path)
    calls: list[list[str]] = []

    async def fake_run(args: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(args)
        if args[0] == "ps":
            return 0, "running|onlyoffice/documentserver:latest", ""
        return 0, "", ""

    manager._run_docker_raw = fake_run  # type: ignore[method-assign]

    state = await manager._inspect(expected_image)

    assert state == ("absent" if removes_stale_container else "running")
    assert (["rm", "-f", "test-office-editor"] in calls) is removes_stale_container


@pytest.mark.unit
@pytest.mark.parametrize(
    ("docker_raw_result", "expected"),
    [
        pytest.param((0, "exited|Exited (0) 2 hours ago", ""), (True, False, "Exited (0) 2 hours ago"), id="exited"),
        pytest.param((0, "", ""), (False, False, None), id="empty_output"),
    ],
)
async def test__inspect_state__pure_read_for_status_api(
    tmp_path: Path, docker_raw_result: tuple[int, str, str], expected: tuple[bool, bool, str | None]
) -> None:
    manager = _make_manager(tmp_path)
    manager._run_docker_raw = AsyncMock(return_value=docker_raw_result)  # type: ignore[method-assign]

    result = await manager.inspect_state()

    assert result == expected


# ── apply_ai_settings ────────────────────────────────────────────────────────

_DS_CONFIG_PATH = "/etc/onlyoffice/documentserver/local.json"


@pytest.mark.unit
async def test__apply_ai_settings__writes_config_and_restarts_docservice(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._probe = AsyncMock(return_value=True)  # type: ignore[method-assign]
    current = '{"services": {"CoAuthoring": {"secret": {"inbox": {"string": "s"}}}}}'
    calls: list[tuple[list[str], bytes | None]] = []

    async def fake_run(args: list[str], timeout: float, stdin: bytes | None = None) -> tuple[int, str, str]:
        calls.append((args, stdin))
        if args[:3] == ["exec", "test-office-editor", "cat"]:
            return 0, current, ""
        return 0, "", ""

    manager._run_docker_raw = fake_run  # type: ignore[method-assign]
    desired = {"version": 3, "proxy": "/ai-proxy", "actions": {"Chat": {"model": "m"}}}

    assert await manager.apply_ai_settings(desired) is True

    write_call = next(c for c in calls if c[0][:2] == ["exec", "-i"])
    assert write_call[0][-1] == f"cat > {_DS_CONFIG_PATH}"
    written = json.loads(write_call[1].decode("utf-8"))
    # aiSettings добавлен, остальной конфиг (JWT-секреты) сохранён как был.
    assert written["aiSettings"] == desired
    assert written["services"]["CoAuthoring"]["secret"]["inbox"]["string"] == "s"
    assert any(c[0][-3:] == ["supervisorctl", "restart", "ds:docservice"] for c in calls)


@pytest.mark.unit
async def test__apply_ai_settings__noop_when_config_matches(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    desired = {"version": 3, "actions": {"Chat": {"model": "m"}}}
    manager._run_docker_raw = AsyncMock(  # type: ignore[method-assign]
        return_value=(0, json.dumps({"aiSettings": desired}), "")
    )

    assert await manager.apply_ai_settings(desired) is True

    manager._run_docker_raw.assert_awaited_once()  # только чтение, без записи/рестарта


@pytest.mark.unit
async def test__apply_ai_settings__refuses_on_unreadable_config(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._run_docker_raw = AsyncMock(return_value=(0, "not-a-json", ""))  # type: ignore[method-assign]

    assert await manager.apply_ai_settings({"version": 3}) is False

    # Битый конфиг не перезаписываем (там живут JWT-секреты DS).
    manager._run_docker_raw.assert_awaited_once()
