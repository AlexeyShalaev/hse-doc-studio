"""Сборка настоящего DI-контейнера.

Остальные тесты используют TestRepositoryProvider, поэтому реальная связка
RepositoryProvider + DomainServiceProvider + UseCaseProvider нигде не проверяется.
dishka валидирует граф при сборке: пропавшая фабрика падает здесь, а не при старте.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.protocols import IAgentRunBus
from hse_doc_studio.core.checks.protocols import ICheckRunner
from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.jobs.protocols import ICompileJobRunner
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.office import IBackendReachability, IOfficeConvertService, IOfficeEditorService
from hse_doc_studio.core.template_materializer import ITemplateMaterializer
from hse_doc_studio.core.update.repositories import ISelfUpdateGateway
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.docker.siblings import Reachability
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.project_init.materializer import TemplateMaterializer
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Синглтон settings общий на процесс: возвращаем его в исходное состояние."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__builds__resolves_core_services() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            gateway = await request_container.get(ISelfUpdateGateway)
            get_project = await request_container.get(GetProjectUC)
            trigger_compile = await request_container.get(TriggerCompileUC)
    finally:
        await container.close()

    assert gateway is not None
    assert isinstance(get_project, GetProjectUC)
    assert isinstance(trigger_compile, TriggerCompileUC)


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__event_buses__port_and_concrete_are_one_singleton() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            agent_bus = await request_container.get(IAgentRunBus)
            agent_bus_concrete = await request_container.get(AgentRunBus)
            log_stream = await request_container.get(IJobLogStream)
            log_bus_concrete = await request_container.get(CompileLogBus)
    finally:
        await container.close()

    assert agent_bus is agent_bus_concrete
    assert log_stream is log_bus_concrete


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__checks_ports__port_and_concrete_are_one_singleton() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            lt_service = await request_container.get(ILanguageCheckService)
            lt_manager = await request_container.get(LanguageToolContainerManager)
            runner_port = await request_container.get(ICheckRunner)
            runner = await request_container.get(CheckRunner)
    finally:
        await container.close()

    assert lt_service is lt_manager
    assert runner_port is runner


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__office_ports__port_and_concrete_are_one_singleton() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            convert_port = await request_container.get(IOfficeConvertService)
            convert_manager = await request_container.get(OfficeConvertManager)
            editor_port = await request_container.get(IOfficeEditorService)
            editor_manager = await request_container.get(OfficeEditorManager)
            reachability_port = await request_container.get(IBackendReachability)
            reachability = await request_container.get(Reachability)
    finally:
        await container.close()

    assert convert_port is convert_manager
    assert editor_port is editor_manager
    assert reachability_port is reachability


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__compile_runner_and_materializer__resolved_as_ports() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            runner = await request_container.get(ICompileJobRunner)
            runner_concrete = await request_container.get(EmbeddedCompileRunner)
            materializer = await request_container.get(ITemplateMaterializer)
    finally:
        await container.close()

    assert isinstance(runner, EmbeddedCompileRunner)
    assert runner is runner_concrete
    assert isinstance(materializer, TemplateMaterializer)
