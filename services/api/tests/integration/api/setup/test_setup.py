from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from hse_doc_studio.core.compile.docker_diagnosis import DockerUnavailableReason, MountFailureReason
from hse_doc_studio.core.setup import MountProbeResult, MountProbeStatus, ProbeEntry
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import (
    OfflineDockerHealthProbe,
    RecordingSetupApplier,
    UnavailableMountProbe,
    create_test_app,
    create_test_container,
)

# Папка, которую «называет пользователь». Записана так, как её примет докер
# (прямые слэши, без хвостового разделителя) — тогда до применителя она обязана
# дойти байт в байт, без нормализации по дороге.
_USER_FOLDER = "D:/study/hse"


async def _client(
    tmp_path: Path,
    *,
    docker_health: OfflineDockerHealthProbe | None = None,
    mount_probe: UnavailableMountProbe | None = None,
    setup_applier: RecordingSetupApplier | None = None,
) -> AsyncGenerator[AsyncClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    container = create_test_container(
        data_dir,
        docker_health=docker_health,
        mount_probe=mount_probe,
        setup_applier=setup_applier,
    )
    app = create_test_app(container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await container.close()


@pytest_asyncio.fixture
async def applier() -> RecordingSetupApplier:
    return RecordingSetupApplier()


@pytest_asyncio.fixture
async def failing_applier() -> RecordingSetupApplier:
    return RecordingSetupApplier(spawns=False)


@pytest_asyncio.fixture
async def readable_folder_probe() -> UnavailableMountProbe:
    # Удачная проба: человек видит СВОИ папки и по ним узнаёт место на диске.
    return UnavailableMountProbe(
        MountProbeResult(
            status=MountProbeStatus.ok,
            exists=True,
            entries=(
                ProbeEntry(name="vkr", is_dir=True),
                ProbeEntry(name="coursework", is_dir=True),
                ProbeEntry(name="notes.md", is_dir=False),
            ),
            is_empty=False,
            writable=True,
        )
    )


@pytest_asyncio.fixture
async def rejected_folder_probe() -> UnavailableMountProbe:
    return UnavailableMountProbe(
        MountProbeResult(
            status=MountProbeStatus.mount_failed,
            reason=MountFailureReason.NOT_SHARED,
            detail="error while creating mount source path",
        )
    )


@pytest_asyncio.fixture
async def app_with_live_docker(tmp_path: Path) -> AsyncGenerator[AsyncClient]:
    async for client in _client(tmp_path, docker_health=OfflineDockerHealthProbe(alive=True)):
        yield client


@pytest_asyncio.fixture
async def app_without_docker_socket(tmp_path: Path) -> AsyncGenerator[AsyncClient]:
    probe = OfflineDockerHealthProbe(alive=False, reason=DockerUnavailableReason.SOCKET_PERMISSION)
    async for client in _client(tmp_path, docker_health=probe):
        yield client


@pytest_asyncio.fixture
async def app_with_readable_folder(
    tmp_path: Path,
    readable_folder_probe: UnavailableMountProbe,
    applier: RecordingSetupApplier,
) -> AsyncGenerator[AsyncClient]:
    async for client in _client(tmp_path, mount_probe=readable_folder_probe, setup_applier=applier):
        yield client


@pytest_asyncio.fixture
async def app_with_rejected_folder(
    tmp_path: Path,
    rejected_folder_probe: UnavailableMountProbe,
    applier: RecordingSetupApplier,
) -> AsyncGenerator[AsyncClient]:
    async for client in _client(tmp_path, mount_probe=rejected_folder_probe, setup_applier=applier):
        yield client


@pytest_asyncio.fixture
async def app_that_cannot_recreate_itself(
    tmp_path: Path,
    readable_folder_probe: UnavailableMountProbe,
    failing_applier: RecordingSetupApplier,
) -> AsyncGenerator[AsyncClient]:
    async for client in _client(tmp_path, mount_probe=readable_folder_probe, setup_applier=failing_applier):
        yield client


# --- status -------------------------------------------------------------------


async def test__api__setup_status__daemon_answers__reports_ready_with_both_checks(
    app_with_live_docker: AsyncClient,
) -> None:
    resp = await app_with_live_docker.get("/api/v1/setup/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Прогон идёт процессом на машине, а не в контейнере: хранилище там — общая
    # файловая система, поэтому единственным блокером мог быть только докер.
    assert body["is_ready"] is True
    assert body["deployment_mode"] == "native"
    checks = {c["id"]: c for c in body["checks"]}
    assert set(checks) == {"docker", "project_storage"}
    assert checks["docker"] == {"id": "docker", "severity": "ok", "code": "ok", "context": {}}
    assert checks["project_storage"]["severity"] == "ok"


async def test__api__setup_status__daemon_is_down__warns_but_keeps_the_app_open(
    app_without_docker_socket: AsyncClient,
) -> None:
    resp = await app_without_docker_socket.get("/api/v1/setup/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    docker = next(c for c in body["checks"] if c["id"] == "docker")
    # Мёртвый демон — состояние машины, а не ошибка установки: его запускают через
    # минуту, ничего не пересоздавая, поэтому запирать весь интерфейс за мастером
    # из-за него нельзя.
    assert docker["severity"] == "warning"
    assert body["is_ready"] is True
    # Код причины доходит до интерфейса неизменным: по нему подбирается и текст,
    # и команда-подсказка.
    assert docker["code"] == "socket_permission"


async def test__api__setup_status__asked_twice__rechecks_the_daemon_every_time(
    tmp_path: Path,
) -> None:
    # Докер могли запустить уже после старта приложения; кэш на процесс заставил
    # бы пользователя перезапускать продукт ради одной этой проверки.
    docker = OfflineDockerHealthProbe(alive=True)

    async for client in _client(tmp_path, docker_health=docker):
        await client.get("/api/v1/setup/status")
        await client.get("/api/v1/setup/status")

    assert docker.calls == 2


# --- probe-folder -------------------------------------------------------------


async def test__api__probe_folder__folder_is_readable__returns_what_lies_in_it(
    app_with_readable_folder: AsyncClient,
    readable_folder_probe: UnavailableMountProbe,
) -> None:
    resp = await app_with_readable_folder.post("/api/v1/setup/probe-folder", json={"host_path": _USER_FOLDER})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "status": "ok",
        "exists": True,
        "entries": [
            {"name": "vkr", "is_dir": True},
            {"name": "coursework", "is_dir": True},
            {"name": "notes.md", "is_dir": False},
        ],
        "is_empty": False,
        "writable": True,
        "looks_like_install": False,
        "free_bytes": None,
        "total_bytes": None,
        "reason": None,
        "detail": None,
    }
    assert readable_folder_probe.probed == [_USER_FOLDER]


async def test__api__probe_folder__path_typed_with_stray_spaces__probes_the_trimmed_one(
    app_with_readable_folder: AsyncClient,
    readable_folder_probe: UnavailableMountProbe,
) -> None:
    # Путь копируют мышью вместе с пробелами, а докер такой источник маунта
    # принимает за другой каталог.
    resp = await app_with_readable_folder.post("/api/v1/setup/probe-folder", json={"host_path": f"  {_USER_FOLDER} "})

    assert resp.status_code == 200, resp.text
    assert readable_folder_probe.probed == [_USER_FOLDER]


async def test__api__probe_folder__daemon_rejected_the_mount__passes_the_reason_through(
    app_with_rejected_folder: AsyncClient,
) -> None:
    resp = await app_with_rejected_folder.post("/api/v1/setup/probe-folder", json={"host_path": _USER_FOLDER})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "mount_failed"
    # По этой паре интерфейс объясняет, что чинить: not_shared — не ошибка
    # продукта, а каталог вне file sharing у Docker Desktop.
    assert body["reason"] == "not_shared"
    assert body["detail"] == "error while creating mount source path"
    assert body["entries"] == []


# --- apply --------------------------------------------------------------------


async def test__api__apply_setup__relative_path__refuses_with_not_absolute_and_never_recreates(
    app_with_readable_folder: AsyncClient,
    readable_folder_probe: UnavailableMountProbe,
    applier: RecordingSetupApplier,
) -> None:
    resp = await app_with_readable_folder.post("/api/v1/setup/apply", json={"host_path": "./data"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is False
    assert body["error_code"] == "not_absolute"
    # Относительный путь докер принял бы за имя тома и молча смонтировал пустоту,
    # поэтому дальше проверки дело не идёт: ни пробы, ни пересоздания.
    assert readable_folder_probe.probed == []
    assert applier.applied_paths == []


async def test__api__apply_setup__blank_path__refuses_with_empty_path(
    app_with_readable_folder: AsyncClient,
    applier: RecordingSetupApplier,
) -> None:
    resp = await app_with_readable_folder.post("/api/v1/setup/apply", json={"host_path": "   "})

    assert resp.status_code == 200, resp.text
    assert resp.json()["error_code"] == "empty_path"
    assert applier.applied_paths == []


async def test__api__apply_setup__probe_did_not_pass__does_not_apply_and_shows_the_probe(
    app_with_rejected_folder: AsyncClient,
    applier: RecordingSetupApplier,
) -> None:
    resp = await app_with_rejected_folder.post("/api/v1/setup/apply", json={"host_path": _USER_FOLDER})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is False
    assert body["error_code"] == "mount_failed"
    # Результат пробы едет вместе с отказом: пересоздание убивает текущий
    # процесс, и второго шанса объяснить причину у мастера не будет.
    assert body["probe"]["reason"] == "not_shared"
    assert applier.applied_paths == []


async def test__api__apply_setup__folder_is_good__applies_exactly_the_path_the_user_typed(
    app_with_readable_folder: AsyncClient,
    readable_folder_probe: UnavailableMountProbe,
    applier: RecordingSetupApplier,
) -> None:
    resp = await app_with_readable_folder.post("/api/v1/setup/apply", json={"host_path": _USER_FOLDER})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # True — пересоздание ЗАПУЩЕНО: интерфейсу остаётся ждать, когда сервер
    # поднимется заново.
    assert body["applied"] is True
    assert body["error_code"] is None
    assert body["probe"]["status"] == "ok"
    assert readable_folder_probe.probed == [_USER_FOLDER]
    assert applier.applied_paths == [_USER_FOLDER]


async def test__api__apply_setup__recreate_did_not_start__reports_recreate_failed(
    app_that_cannot_recreate_itself: AsyncClient,
    failing_applier: RecordingSetupApplier,
) -> None:
    resp = await app_that_cannot_recreate_itself.post("/api/v1/setup/apply", json={"host_path": _USER_FOLDER})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Приложение осталось живым и обязано сказать об этом: молчаливое «applied»
    # оставило бы интерфейс ждать перезапуска, которого не будет.
    assert body["applied"] is False
    assert body["error_code"] == "recreate_failed"
    assert failing_applier.applied_paths == [_USER_FOLDER]
