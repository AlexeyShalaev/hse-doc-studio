from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.compile.docker_image_manager import DockerStatus, ImageInfo
from hse_doc_studio.use_cases.office_services.get_office_services_status import (
    GetOfficeServicesStatusUC,
)
from hse_doc_studio.use_cases.office_services.install_office_service_image import (
    InstallOfficeServiceImageInput,
    InstallOfficeServiceImageUC,
)
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    office_repo_allowed,
    resolve_active_office_image,
)
from hse_doc_studio.use_cases.office_services.list_office_service_remote_tags import (
    ListOfficeServiceRemoteTagsInput,
    ListOfficeServiceRemoteTagsUC,
)
from hse_doc_studio.use_cases.office_services.set_active_office_service_image import (
    SetActiveOfficeServiceImageInput,
    SetActiveOfficeServiceImageUC,
)


def _settings_repo(stored: dict[str, Any] | None = None) -> MagicMock:
    repo = MagicMock()
    repo.get.return_value = dict(stored or {})
    return repo


def _image_info(image: str) -> ImageInfo:
    return ImageInfo(image=image, id="sha256:abc", size_bytes=100, created="2026-01-01")


# ── resolve_active_office_image ────────────────────────────────────────────


@pytest.mark.unit
def test__resolve_active_office_image__defaults_from_api_config() -> None:
    repo = _settings_repo()

    assert resolve_active_office_image(repo, "convert") == "gotenberg/gotenberg:8"
    assert resolve_active_office_image(repo, "editor") == "onlyoffice/documentserver:latest"


@pytest.mark.unit
def test__resolve_active_office_image__settings_override_wins() -> None:
    repo = _settings_repo(
        {
            "office_convert_image": "gotenberg/gotenberg:9",
            "office_editor_image": "onlyoffice/documentserver:9.0",
        }
    )

    assert resolve_active_office_image(repo, "convert") == "gotenberg/gotenberg:9"
    assert resolve_active_office_image(repo, "editor") == "onlyoffice/documentserver:9.0"


@pytest.mark.unit
def test__resolve_active_office_image__blank_override_falls_back() -> None:
    repo = _settings_repo({"office_convert_image": "   ", "office_editor_image": None})

    assert resolve_active_office_image(repo, "convert") == "gotenberg/gotenberg:8"
    assert resolve_active_office_image(repo, "editor") == "onlyoffice/documentserver:latest"


@pytest.mark.unit
def test__resolve_active_office_image__unknown_service_raises() -> None:
    with pytest.raises(ValueError, match="неизвестный офисный сервис"):
        resolve_active_office_image(_settings_repo(), "languagetool")


@pytest.mark.unit
def test__office_repo_allowed__requires_tag_and_allowlisted_repo() -> None:
    allowed = ["gotenberg/gotenberg"]

    assert office_repo_allowed("gotenberg/gotenberg:8", allowed)
    assert not office_repo_allowed("gotenberg/gotenberg", allowed)  # без тега
    assert not office_repo_allowed("evil/gotenberg:8", allowed)


# ── set active ─────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "image",
    [
        "evil/image:1",
        "onlyoffice/documentserver:latest",  # редакторский образ нельзя активировать для convert-сервиса
    ],
)
async def test__set_active__rejects_image_outside_allowlist(image: str) -> None:
    image_manager = MagicMock()
    image_manager.inspect = AsyncMock(return_value=_image_info("evil/image:1"))
    repo = _settings_repo()
    uc = SetActiveOfficeServiceImageUC(image_manager=image_manager, settings_repo=repo)

    with pytest.raises(ValueError, match="разрешённых репозиториев"):
        await uc.execute(SetActiveOfficeServiceImageInput(service="convert", image=image))

    repo.save.assert_not_called()


@pytest.mark.unit
async def test__set_active__rejects_not_installed_image() -> None:
    image_manager = MagicMock()
    image_manager.inspect = AsyncMock(return_value=None)
    repo = _settings_repo()
    uc = SetActiveOfficeServiceImageUC(image_manager=image_manager, settings_repo=repo)

    with pytest.raises(NotFoundError, match="не установлен локально"):
        await uc.execute(SetActiveOfficeServiceImageInput(service="editor", image="onlyoffice/documentserver:9.0"))
    repo.save.assert_not_called()


@pytest.mark.unit
async def test__set_active__persists_per_service_settings_key() -> None:
    image_manager = MagicMock()
    image_manager.inspect = AsyncMock(return_value=_image_info("gotenberg/gotenberg:9"))
    repo = _settings_repo({"theme": "dark"})
    uc = SetActiveOfficeServiceImageUC(image_manager=image_manager, settings_repo=repo)

    out = await uc.execute(SetActiveOfficeServiceImageInput(service="convert", image="gotenberg/gotenberg:9"))

    assert out.image == "gotenberg/gotenberg:9"
    saved = repo.save.call_args.args[0]
    assert saved["office_convert_image"] == "gotenberg/gotenberg:9"
    assert saved["theme"] == "dark"  # остальные настройки не потеряны


# ── status ─────────────────────────────────────────────────────────────────


def _status_uc(
    *,
    docker_available: bool = True,
    convert_state: tuple[bool, bool, str | None] = (True, False, "Exited (0) 2 hours ago"),
    editor_state: tuple[bool, bool, str | None] = (False, False, None),
    installed_images: set[str] | None = None,
    stored: dict[str, Any] | None = None,
) -> tuple[GetOfficeServicesStatusUC, MagicMock, MagicMock]:
    convert_manager = MagicMock()
    convert_manager.inspect_state = AsyncMock(return_value=convert_state)
    editor_manager = MagicMock()
    editor_manager.inspect_state = AsyncMock(return_value=editor_state)
    image_manager = MagicMock()
    image_manager.docker_status = AsyncMock(
        return_value=DockerStatus(available=docker_available, version="27.0", detail=None)
    )
    installed = installed_images or set()
    image_manager.inspect = AsyncMock(side_effect=lambda image: _image_info(image) if image in installed else None)
    uc = GetOfficeServicesStatusUC(
        convert_manager=convert_manager,
        editor_manager=editor_manager,
        image_manager=image_manager,
        settings_repo=_settings_repo(stored),
    )
    return uc, convert_manager, editor_manager


@pytest.mark.unit
async def test__status__reports_both_services_with_container_state() -> None:
    uc, _convert, _editor = _status_uc(installed_images={"gotenberg/gotenberg:8"})

    out = await uc.execute()

    assert [s.service for s in out.services] == ["convert", "editor"]
    convert, editor = out.services
    assert convert.label_hint == "gotenberg"
    assert convert.active_image == "gotenberg/gotenberg:8"
    assert convert.image_installed is True
    assert convert.container.present is True
    assert convert.container.running is False
    assert convert.container.status_text == "Exited (0) 2 hours ago"
    assert editor.label_hint == "onlyoffice"
    assert editor.active_image == "onlyoffice/documentserver:latest"
    assert editor.image_installed is False
    assert editor.container.present is False
    assert editor.container.status_text is None


@pytest.mark.unit
async def test__status__uses_runtime_active_image() -> None:
    uc, _convert, _editor = _status_uc(
        installed_images={"gotenberg/gotenberg:9"},
        stored={"office_convert_image": "gotenberg/gotenberg:9"},
    )

    out = await uc.execute()

    assert out.services[0].active_image == "gotenberg/gotenberg:9"
    assert out.services[0].image_installed is True


@pytest.mark.unit
async def test__status__docker_unavailable__containers_absent_and_managers_untouched() -> None:
    uc, convert_manager, editor_manager = _status_uc(docker_available=False)

    out = await uc.execute()

    for service in out.services:
        assert service.image_installed is False
        assert service.container.present is False
        assert service.container.running is False
        assert service.container.status_text is None
    convert_manager.inspect_state.assert_not_awaited()
    editor_manager.inspect_state.assert_not_awaited()


# ── install (только валидация; сам pull не тестируем) ──────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("image", ["evil/image:1", "gotenberg/gotenberg:8"])
async def test__install__rejects_image_outside_allowlist(image: str) -> None:
    image_manager = MagicMock()
    image_manager.pull = AsyncMock()
    uc = InstallOfficeServiceImageUC(image_manager=image_manager)

    with pytest.raises(ValueError, match="разрешённых репозиториев"):
        await uc.execute(InstallOfficeServiceImageInput(service="editor", image=image))

    image_manager.pull.assert_not_awaited()


@pytest.mark.unit
async def test__install__allowed_image_starts_pull_stream() -> None:
    image_manager = MagicMock()
    stream = object()
    image_manager.pull = AsyncMock(return_value=stream)
    uc = InstallOfficeServiceImageUC(image_manager=image_manager)

    result = await uc.execute(InstallOfficeServiceImageInput(service="convert", image="gotenberg/gotenberg:9"))

    assert result is stream
    image_manager.pull.assert_awaited_once_with("gotenberg/gotenberg:9")


# ── remote tags ────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test__remote_tags__defaults_to_first_allowed_repo() -> None:
    image_manager = MagicMock()
    image_manager.list_remote_tags = AsyncMock(return_value=[])
    uc = ListOfficeServiceRemoteTagsUC(image_manager=image_manager)

    out = await uc.execute(ListOfficeServiceRemoteTagsInput(service="convert", repo=None))

    assert out.repo == "gotenberg/gotenberg"
    image_manager.list_remote_tags.assert_awaited_once_with("gotenberg/gotenberg", "https://hub.docker.com/v2")


@pytest.mark.unit
async def test__remote_tags__rejects_repo_outside_allowlist() -> None:
    image_manager = MagicMock()
    image_manager.list_remote_tags = AsyncMock(return_value=[])
    uc = ListOfficeServiceRemoteTagsUC(image_manager=image_manager)

    with pytest.raises(ValueError, match="репозиторий не разрешён"):
        await uc.execute(ListOfficeServiceRemoteTagsInput(service="editor", repo="gotenberg/gotenberg"))
    image_manager.list_remote_tags.assert_not_awaited()
