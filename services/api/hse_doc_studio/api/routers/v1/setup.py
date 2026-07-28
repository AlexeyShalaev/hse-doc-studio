"""Мастер первоначальной настройки: диагностика установки и её починка.

Три ручки и ровно один сценарий между ними: спросить состояние → проверить
папку, которую назвал пользователь → применить. Ручка проверки отделена от
применения намеренно: пересоздание контейнера убивает текущий процесс, и
предлагать его вслепую, не показав человеку содержимое папки, нельзя.
"""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel, Field

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.fonts.repositories import ISystemFontProvider
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.setup import (
    IEnvironmentProbe,
    IMountProbe,
    MountProbeResult,
    SetupCheck,
)
from hse_doc_studio.infra.docker.cli import image_present
from hse_doc_studio.infra.update.deployment import DeploymentMode, deployment_mode
from hse_doc_studio.use_cases.compile.list_images import resolve_active_image
from hse_doc_studio.use_cases.setup.apply_setup import ApplySetupInput, ApplySetupUC
from hse_doc_studio.use_cases.setup.inspect_setup import InspectSetupUC

router = APIRouter(route_class=DishkaRoute)


class SetupCheckResponse(BaseModel):
    id: str
    severity: str
    # Машиночитаемый код причины: текст подбирает интерфейс по своим словарям.
    code: str
    context: dict[str, str] = Field(default_factory=dict)


class SetupStatusResponse(BaseModel):
    # False — интерфейс обязан показать мастер вместо рабочего экрана.
    is_ready: bool
    deployment_mode: DeploymentMode
    checks: list[SetupCheckResponse]
    # Имя compose-проекта, если контейнер поднят им. Такую установку мастер не
    # чинит сам: следующий `docker compose up -d` вернул бы старую конфигурацию.
    compose_project: str | None = None
    can_self_apply: bool = True
    # Версия — единственное, что стартовый экран может сказать о себе сам:
    # «О программе» за мастером ещё не доступна.
    app_version: str


class ProbeFolderRequest(BaseModel):
    host_path: str


class ProbeEntryResponse(BaseModel):
    name: str
    is_dir: bool


class ProbeFolderResponse(BaseModel):
    status: str
    # Есть ли такая папка. Отдельно от `is_empty`: несуществующий путь и пустой
    # каталог — разные вещи, и путать их нельзя, иначе опечатка выглядит как
    # успех.
    exists: bool = False
    # Содержимое: по нему человек узнаёт своё место на диске и ходит вглубь.
    entries: list[ProbeEntryResponse] = Field(default_factory=list)
    is_empty: bool = False
    writable: bool = False
    # Папка похожа на каталог данных прежней установки: проекты и настройки
    # из неё подхватятся, о чём мастер говорит явно.
    looks_like_install: bool = False
    # Сколько места осталось на диске с этой папкой: на первой сборке докер
    # скачивает образ TeX Live в несколько гигабайт.
    free_bytes: int | None = None
    total_bytes: int | None = None
    reason: str | None = None
    detail: str | None = None


class ApplySetupRequest(BaseModel):
    host_path: str
    # Каталог шрифтов на хосте, если автоопределение промахнулось.
    fonts_host_path: str | None = None
    # Скачивать ли движок LaTeX фоном после пересоздания.
    prefetch_tex_image: bool = True


class ApplySetupResponse(BaseModel):
    # True — приложение уже пересоздаётся; текущее соединение вот-вот оборвётся,
    # и интерфейсу остаётся дождаться, когда сервер поднимется заново.
    applied: bool
    error_code: str | None = None
    probe: ProbeFolderResponse | None = None


def _probe(result: MountProbeResult) -> ProbeFolderResponse:
    return ProbeFolderResponse(
        status=str(result.status),
        exists=result.exists,
        entries=[ProbeEntryResponse(name=e.name, is_dir=e.is_dir) for e in result.entries],
        is_empty=result.is_empty,
        writable=result.writable,
        looks_like_install=result.looks_like_install,
        free_bytes=result.free_bytes,
        total_bytes=result.total_bytes,
        reason=str(result.reason) if result.reason is not None else None,
        detail=result.detail,
    )


def _check(check: SetupCheck) -> SetupCheckResponse:
    return SetupCheckResponse(
        id=str(check.id),
        severity=str(check.severity),
        code=check.code,
        context=dict(check.context),
    )


@router.get("/setup/status", response_model=SetupStatusResponse)
async def setup_status(uc: FromDishka[InspectSetupUC]) -> SetupStatusResponse:
    result = await uc.execute()
    return SetupStatusResponse(
        is_ready=result.report.is_ready,
        deployment_mode=deployment_mode(settings.static_dir),
        checks=[_check(c) for c in result.report.checks],
        compose_project=result.report.compose_project,
        can_self_apply=result.report.can_self_apply,
        app_version=settings.get_app_version(),
    )


@router.post("/setup/probe-folder", response_model=ProbeFolderResponse)
async def probe_folder(payload: ProbeFolderRequest, probe: FromDishka[IMountProbe]) -> ProbeFolderResponse:
    result = await probe.probe(payload.host_path.strip())
    return _probe(result)


@router.post("/setup/apply", response_model=ApplySetupResponse)
async def apply_setup(payload: ApplySetupRequest, uc: FromDishka[ApplySetupUC]) -> ApplySetupResponse:
    result = await uc.execute(
        ApplySetupInput(
            host_path=payload.host_path,
            fonts_host_path=payload.fonts_host_path,
            prefetch_tex_image=payload.prefetch_tex_image,
        )
    )
    return ApplySetupResponse(
        applied=result.applied,
        error_code=result.error_code,
        probe=_probe(result.probe) if result.probe is not None else None,
    )


# ---------------------------------------------------------------- окружение


class DockerEngineResponse(BaseModel):
    server_version: str
    os_type: str
    operating_system: str
    architecture: str
    # Ресурсы, доступные КОНТЕЙНЕРАМ: на Docker Desktop это квота виртуальной
    # машины, а не всё железо. Именно от неё зависит скорость сборок.
    cpus: int
    memory_bytes: int


class ContainerMountResponse(BaseModel):
    source: str
    destination: str
    read_only: bool


class ContainerRuntimeResponse(BaseModel):
    image: str
    published_ports: list[str] = Field(default_factory=list)
    mounts: list[ContainerMountResponse] = Field(default_factory=list)
    socket_mounted: bool
    group_add: list[str] = Field(default_factory=list)
    restart_policy: str
    network_mode: str


class HostFontsResponse(BaseModel):
    # Каталог, из которого приложение возьмёт шрифты пользователя. null —
    # ни одно стандартное место не подошло, и путь нужно указать руками.
    directory: str | None = None
    count: int = 0


class TexImageResponse(BaseModel):
    """Движок LaTeX: скачан ли уже. Не скачан — первая сборка начнётся с
    многогигабайтной загрузки, и предупредить об этом надо здесь."""

    image: str
    present: bool


class SetupEnvironmentResponse(BaseModel):
    engine: DockerEngineResponse | None = None
    container: ContainerRuntimeResponse | None = None
    fonts: HostFontsResponse | None = None
    tex: TexImageResponse | None = None


@router.get("/setup/environment", response_model=SetupEnvironmentResponse)
async def setup_environment(
    probe: FromDishka[IEnvironmentProbe],
    fonts: FromDishka[ISystemFontProvider],
    settings_repo: FromDishka[ISettingsRepository],
) -> SetupEnvironmentResponse:
    """Что за машина под нами и с какими параметрами нас запустили.

    Отдельно от `/setup/status`: `docker info` не мгновенен, а статус
    опрашивается в цикле, пока приложение пересоздаётся.
    """
    described = await probe.describe()
    engine = described.engine
    container = described.container
    # Перебор каталогов шрифтов идёт одноразовыми контейнерами и кэшируется на
    # процесс — здесь это первый и единственный запуск за сеанс.
    font_dir = await fonts.source_dir()
    font_files = await fonts.list_fonts() if font_dir else []
    # Наличие образа не кэшируем: предзагрузка идёт фоном, и «скачан» обязан
    # появиться без перезапуска.
    tex_image = resolve_active_image(settings_repo)
    tex_present = await image_present(tex_image)
    return SetupEnvironmentResponse(
        engine=DockerEngineResponse(**vars(engine)) if engine is not None else None,
        container=(
            ContainerRuntimeResponse(
                image=container.image,
                published_ports=list(container.published_ports),
                mounts=[ContainerMountResponse(**vars(m)) for m in container.mounts],
                socket_mounted=container.socket_mounted,
                group_add=list(container.group_add),
                restart_policy=container.restart_policy,
                network_mode=container.network_mode,
            )
            if container is not None
            else None
        ),
        fonts=HostFontsResponse(directory=font_dir, count=len(font_files)),
        tex=TexImageResponse(image=tex_image, present=tex_present),
    )
