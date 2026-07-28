from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    OFFICE_SERVICES,
    office_service_label_hint,
    resolve_active_office_image,
)


@dataclass
class OfficeServiceContainerState:
    present: bool
    running: bool
    status_text: str | None


@dataclass
class OfficeServiceStatus:
    service: str
    label_hint: str
    active_image: str
    image_installed: bool
    container: OfficeServiceContainerState


@dataclass
class OfficeServicesStatusOutput:
    services: list[OfficeServiceStatus]


class GetOfficeServicesStatusUC:
    """Aggregates what the Settings UI needs to render both office services
    (Gotenberg convert + ONLYOFFICE editor): the active image, whether it is
    installed, and the managed container's presence/state. Mirrors
    GetLanguageToolStatusUC; installing the image is the opt-in — there is no
    enable flag or configurable URL.
    """

    def __init__(
        self,
        convert_manager: OfficeConvertManager,
        editor_manager: OfficeEditorManager,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._managers: dict[str, OfficeConvertManager | OfficeEditorManager] = {
            "convert": convert_manager,
            "editor": editor_manager,
        }
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self) -> OfficeServicesStatusOutput:
        docker_status = await self._image_manager.docker_status()
        services: list[OfficeServiceStatus] = []
        for service in OFFICE_SERVICES:
            active_image = resolve_active_office_image(self._settings_repo, service)
            image_installed = False
            container = OfficeServiceContainerState(present=False, running=False, status_text=None)
            if docker_status.available:
                image_installed = await self._image_manager.inspect(active_image) is not None
                present, running, status_text = await self._managers[service].inspect_state()
                container = OfficeServiceContainerState(present=present, running=running, status_text=status_text)
            services.append(
                OfficeServiceStatus(
                    service=service,
                    label_hint=office_service_label_hint(service),
                    active_image=active_image,
                    image_installed=image_installed,
                    container=container,
                )
            )
        return OfficeServicesStatusOutput(services=services)
