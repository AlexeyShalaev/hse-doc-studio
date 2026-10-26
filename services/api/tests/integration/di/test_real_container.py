"""Сборка настоящего DI-контейнера.

Остальные тесты используют TestRepositoryProvider, поэтому реальная связка
RepositoryProvider + DomainServiceProvider + UseCaseProvider нигде не проверяется.
dishka валидирует граф при сборке: пропавшая фабрика падает здесь, а не при старте.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.protocols import IAgentRunBus
from hse_doc_studio.core.checks.protocols import ICheckRunner
from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict, Lang
from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.jobs.entities import JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.office import OfficeConvertPayload, OfficeConvertResult, OfficeConvertStatus
from hse_doc_studio.core.jobs.protocols import ICompileJobRunner, IJobDispatcher
from hse_doc_studio.core.jobs.verify import VerifyDetachedPayload, VerifyDetachedResult
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.office import IBackendReachability, IOfficeConvertService, IOfficeEditorService
from hse_doc_studio.core.signatures.ports import (
    IChainFetcher,
    IOpenPgpKeyImporter,
    IPublicKeyExporter,
    ITrustMaterialProvider,
)
from hse_doc_studio.core.template_materializer import ITemplateMaterializer
from hse_doc_studio.core.update.repositories import ISelfUpdateGateway
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.docker.siblings import Reachability
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.jobs.local_dispatcher import LocalJobDispatcher
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.project_init.materializer import TemplateMaterializer
from hse_doc_studio.infra.signatures.chain_fetcher import ChainFetcher
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.trust_material import LocalTrustMaterialProvider
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC

from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity


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
async def test__real_container__public_key_exporter__port_and_keyring_are_one_singleton() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            exporter = await request_container.get(IPublicKeyExporter)
            keyring = await request_container.get(GpgKeyring)
    finally:
        await container.close()

    assert exporter is keyring


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


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__job_dispatcher_and_handler_registry__resolved_as_singletons() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            dispatcher = await request_container.get(IJobDispatcher)
            handlers = await request_container.get(JobHandlerRegistry)
        async with container() as another_request:
            dispatcher_again = await another_request.get(IJobDispatcher)
    finally:
        await container.close()

    assert isinstance(dispatcher, LocalJobDispatcher)
    assert isinstance(handlers, JobHandlerRegistry)
    assert dispatcher is dispatcher_again


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__office_convert_job__runs_through_the_registered_handler(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "tz").mkdir(parents=True)
    (project / "tz" / "ТЗ.docx").write_bytes(b"docx")
    spec = JobSpec(
        id=uuid4(),
        kind=JobKind.office_convert,
        tags=frozenset({"office"}),
        project_id=uuid4(),
        actor=Actor.local(),
        locale=Lang.ru,
        payload=OfficeConvertPayload(source=ManifestFile("tz/ТЗ.docx"), output_path="tz/ТЗ.pdf"),
        local_root=project,
    )
    container = create_container()
    try:
        async with container() as request_container:
            dispatcher = await request_container.get(IJobDispatcher)
            manager = await request_container.get(OfficeConvertManager)
            with patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=b"%PDF") as convert:
                result = await dispatcher.run(spec)
    finally:
        await container.close()

    assert result.status is JobStatus.succeeded
    assert result.data_as(OfficeConvertResult).status is OfficeConvertStatus.ok
    assert (project / "tz" / "ТЗ.pdf").read_bytes() == b"%PDF"
    # Порт и конкретный менеджер в обработчике одно и то же: конвертер вызван на этом экземпляре.
    assert convert.await_args.args[0] is manager


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__signature_ports__port_and_concrete_are_one_singleton() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            importer = await request_container.get(IOpenPgpKeyImporter)
            keyring = await request_container.get(GpgKeyring)
            fetcher_port = await request_container.get(IChainFetcher)
            fetcher = await request_container.get(ChainFetcher)
        async with container() as another_request:
            keyring_again = await another_request.get(GpgKeyring)
    finally:
        await container.close()

    assert importer is keyring
    assert fetcher_port is fetcher
    assert keyring is keyring_again


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__trust_material_provider__port_and_concrete_are_one_singleton() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            port = await request_container.get(ITrustMaterialProvider)
            concrete = await request_container.get(LocalTrustMaterialProvider)
        async with container() as another_request:
            concrete_again = await another_request.get(LocalTrustMaterialProvider)
    finally:
        await container.close()

    assert port is concrete
    assert concrete is concrete_again


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__verify_job_for_a_gost_signature__runs_through_the_dispatcher(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    pdf = b"%PDF-1.7 body"
    (workspace / "frozen.pdf").write_bytes(pdf)
    identity = make_identity()
    container = create_container()
    try:
        async with container() as request_container:
            dispatcher = await request_container.get(IJobDispatcher)
            trust = await request_container.get(ITrustMaterialProvider)
            payload = VerifyDetachedPayload(
                pdf=ManifestFile("frozen.pdf"),
                signature=InlineBlob.from_bytes(make_detached_cms(identity, pdf)),
                trust=trust.snapshot(),
            )
            spec = JobSpec(
                id=uuid4(),
                kind=JobKind.verify_detached,
                tags=job_tags(JobKind.verify_detached, payload),
                project_id=uuid4(),
                actor=Actor.local(),
                locale=Lang.ru,
                payload=payload,
                local_root=workspace,
            )

            result = await dispatcher.run(spec)
    finally:
        await container.close()

    assert result.status is JobStatus.succeeded, result.error
    verified = result.data_as(VerifyDetachedResult).signature
    assert verified.format is DetachedFormat.cms
    assert verified.verdict is DetachedVerdict.valid
