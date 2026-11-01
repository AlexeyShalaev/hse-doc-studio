"""Смоук DI: режим выбирает провайдеры, local не меняется, server собирается с подставным engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from dishka.exceptions import NoFactoryError
from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC

pytest.importorskip("sqlalchemy")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)


async def test__local_container__has_no_server_ports() -> None:
    container = create_container(StudioMode.local)
    try:
        async with container() as request:
            repo = await request.get(IProjectRepository)
            with pytest.raises(NoFactoryError):
                await request.get(IUnitOfWork)
    finally:
        await container.close()

    assert isinstance(repo, JsonProjectRepository)


async def test__server_container__fake_engine__resolves_uow_config_and_use_cases() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")  # ленивый, соединения не откроет
    container = create_container(StudioMode.server, engine=engine)
    try:
        async with container() as request:
            uow = await request.get(IUnitOfWork)
            server_cfg = await request.get(ServerConfig)
            get_project = await request.get(GetProjectUC)
    finally:
        await container.close()
        await engine.dispose()

    assert hasattr(uow, "begin")
    assert server_cfg.projects_root == Path(settings.data_dir) / "projects"
    assert isinstance(get_project, GetProjectUC)


async def test__server_container__resolves_actor_resolver_chain() -> None:
    from hse_doc_studio.core.identity.protocols import IActorResolver
    from hse_doc_studio.infra.identity.resolvers import ChainActorResolver
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        resolver = await container.get(IActorResolver)
    finally:
        await container.close()
        await engine.dispose()

    assert isinstance(resolver, ChainActorResolver)


async def test__server_container__resolves_the_setup_wizard_use_cases() -> None:
    from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC, EnsureBootstrapAdminUC
    from hse_doc_studio.use_cases.server_setup.settings import ApplyInitialSettingsUC, CompleteSetupUC
    from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService
    from hse_doc_studio.use_cases.server_setup.token import SetupToken
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        resolved = [
            await container.get(kind)
            for kind in (
                CreateFirstAdminUC,
                EnsureBootstrapAdminUC,
                ApplyInitialSettingsUC,
                CompleteSetupUC,
                GetSetupStatusUC,
            )
        ]
        state, token = await container.get(SetupStateService), await container.get(SetupToken)
        same_token = await container.get(SetupToken)
    finally:
        await container.close()
        await engine.dispose()

    assert len(resolved) == 5
    assert isinstance(state, SetupStateService)
    # Токен один на процесс: иначе в журнал попал бы один, а проверялся другой.
    assert token is same_token


def test__local_container__does_not_import_server_modules() -> None:
    for name in list(sys.modules):
        if name.startswith("hse_doc_studio.infra.di.providers.server_"):
            del sys.modules[name]

    create_container(StudioMode.local)

    assert "hse_doc_studio.infra.di.providers.server_persistence" not in sys.modules


async def test__server_container__resolves_postgres_project_locator_and_volume() -> None:
    from hse_doc_studio.core.projects.locator import IProjectLocator
    from hse_doc_studio.core.projects.volume import IProjectVolume
    from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
    from hse_doc_studio.infra.projects.catalog_sync import MirroringProjectRepository, ProjectCatalogReconciler
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        async with container() as request:
            locator = await request.get(IProjectLocator)
            volume = await request.get(IProjectVolume)
            repo = await request.get(IProjectRepository)
            reconciler = await request.get(ProjectCatalogReconciler)
    finally:
        await container.close()
        await engine.dispose()

    assert isinstance(locator, PostgresProjectLocator)
    assert isinstance(repo, MirroringProjectRepository)
    assert isinstance(reconciler, ProjectCatalogReconciler)
    assert volume.root == Path(settings.data_dir) / "projects"


async def test__server_container__settings_repo_is_postgres_while_local_stays_json(tmp_path: Path) -> None:
    from hse_doc_studio.core.repositories import ISettingsRepository  # noqa: PLC0415
    from hse_doc_studio.infra.db.repositories.settings import PostgresSettingsRepository  # noqa: PLC0415
    from hse_doc_studio.infra.persistence.settings import JsonSettingsRepository  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_repo = await request.get(ISettingsRepository)
        async with server() as request:
            server_repo = await request.get(ISettingsRepository)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_repo, JsonSettingsRepository)
    assert isinstance(server_repo, PostgresSettingsRepository)


async def test__server_container__compile_repo_is_postgres_while_local_stays_json() -> None:
    from hse_doc_studio.core.repositories import ICompileRepository  # noqa: PLC0415
    from hse_doc_studio.infra.db.repositories.compile import PostgresCompileRepository  # noqa: PLC0415
    from hse_doc_studio.infra.persistence.compile import JsonCompileRepository  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_repo = await request.get(ICompileRepository)
        async with server() as request:
            server_repo = await request.get(ICompileRepository)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_repo, JsonCompileRepository)
    assert isinstance(server_repo, PostgresCompileRepository)


async def test__server_container__chat_repo_is_postgres_while_local_stays_json() -> None:
    from hse_doc_studio.core.repositories import IChatRepository  # noqa: PLC0415
    from hse_doc_studio.infra.db.repositories.chat import PostgresChatRepository  # noqa: PLC0415
    from hse_doc_studio.infra.persistence.chat import JsonChatRepository  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_repo = await request.get(IChatRepository)
        async with server() as request:
            server_repo = await request.get(IChatRepository)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_repo, JsonChatRepository)
    assert isinstance(server_repo, PostgresChatRepository)


async def test__server_container__artifact_store_is_s3_while_local_stays_on_disk() -> None:
    from hse_doc_studio.core.jobs.artifacts import IArtifactStore  # noqa: PLC0415
    from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore  # noqa: PLC0415
    from hse_doc_studio.infra.jobs.s3_artifact_store import S3ArtifactStore  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_store = await request.get(IArtifactStore)
        async with server() as request:
            server_store = await request.get(IArtifactStore)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_store, LocalDiskArtifactStore)
    assert isinstance(server_store, S3ArtifactStore)


async def test__server_container__job_storage_and_live_blobs_use_the_object_store() -> None:
    from hse_doc_studio.core.jobs.storage import IJobBlobStore, IJobOutputIngest
    from hse_doc_studio.core.storage.manifest import ILiveBlobSource
    from hse_doc_studio.infra.jobs.live_blobs import QueueLiveBlobs
    from hse_doc_studio.infra.jobs.object_storage import AnnouncedJobOutputIngest, ObjectJobBlobStore
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        blobs = await container.get(IJobBlobStore)
        outputs = await container.get(IJobOutputIngest)
        live = await container.get(ILiveBlobSource)
    finally:
        await container.close()
        await engine.dispose()

    assert isinstance(blobs, ObjectJobBlobStore)
    assert isinstance(outputs, AnnouncedJobOutputIngest)
    assert isinstance(live, QueueLiveBlobs)


async def test__server_container__resolves_the_admin_ops_use_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.fernet import Fernet
    from hse_doc_studio.use_cases.admin.ops_ai_providers import (
        CheckInstanceAiProviderUC,
        CreateInstanceAiProviderUC,
        DeleteInstanceAiProviderUC,
        GetInstanceAiProviderUC,
        ListInstanceAiProvidersUC,
        UpdateInstanceAiProviderUC,
    )
    from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, ListQueueUC, QueueSummaryUC
    from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, QuotaService, UpdateQuotasUC
    from hse_doc_studio.use_cases.admin.ops_services import ServicesOverviewUC
    from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
    from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC
    from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import create_async_engine

    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    kinds = [
        ListQueueUC,
        QueueSummaryUC,
        CancelJobUC,
        GetQuotasUC,
        UpdateQuotasUC,
        ServicesOverviewUC,
        GetStorageUsageUC,
        GetSigningPolicyUC,
        UpdateSigningPolicyUC,
        ListInstanceAiProvidersUC,
        GetInstanceAiProviderUC,
        CreateInstanceAiProviderUC,
        UpdateInstanceAiProviderUC,
        DeleteInstanceAiProviderUC,
        CheckInstanceAiProviderUC,
        RunnerJobService,
    ]
    try:
        resolved = [await container.get(kind) for kind in kinds]
        quotas = await container.get(QuotaService)
        again = await container.get(QuotaService)
    finally:
        await container.close()
        await engine.dispose()

    assert [type(r) for r in resolved] == kinds
    assert quotas is again


async def test__server_container__dispatcher_is_the_queue_one_while_local_stays_embedded() -> None:
    from hse_doc_studio.core.jobs.protocols import IJobDispatcher  # noqa: PLC0415
    from hse_doc_studio.infra.jobs.local_dispatcher import LocalJobDispatcher  # noqa: PLC0415
    from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        local_dispatcher = await local.get(IJobDispatcher)
        server_dispatcher = await server.get(IJobDispatcher)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_dispatcher, LocalJobDispatcher)
    assert isinstance(server_dispatcher, QueueJobDispatcher)


async def test__server_container__ai_provider_repo_is_postgres_while_local_stays_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cryptography.fernet import Fernet  # noqa: PLC0415
    from hse_doc_studio.core.repositories import IAIProviderRepository  # noqa: PLC0415
    from hse_doc_studio.infra.db.repositories.ai_providers import PostgresAIProviderRepository  # noqa: PLC0415
    from hse_doc_studio.infra.persistence.ai_provider import JsonAIProviderRepository  # noqa: PLC0415
    from hse_doc_studio.use_cases.ai_providers.create_ai_provider import CreateAIProviderUC  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_repo = await request.get(IAIProviderRepository)
            local_create = await request.get(CreateAIProviderUC)
        async with server() as request:
            server_repo = await request.get(IAIProviderRepository)
            server_create = await request.get(CreateAIProviderUC)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_repo, JsonAIProviderRepository)
    assert isinstance(server_repo, PostgresAIProviderRepository)
    # В local адрес провайдера не проверяется, в server проверяется политикой egress
    assert local_create._egress is None  # noqa: SLF001
    assert server_create._egress is not None  # noqa: SLF001


async def test__server_container__signing_identity_repo_is_postgres_with_default_deny_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cryptography.fernet import Fernet  # noqa: PLC0415
    from hse_doc_studio.core.repositories import ISigningIdentityRepository  # noqa: PLC0415
    from hse_doc_studio.core.signatures.key_policy import ISigningKeyPolicy  # noqa: PLC0415
    from hse_doc_studio.infra.db.repositories.signing_identities import (  # noqa: PLC0415
        PostgresSigningIdentityRepository,
    )
    from hse_doc_studio.infra.db.repositories.signing_key_policy import InstanceSigningKeyPolicy  # noqa: PLC0415
    from hse_doc_studio.infra.persistence.signing_identity import JsonSigningIdentityRepository  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_repo = await request.get(ISigningIdentityRepository)
        async with server() as request:
            server_repo = await request.get(ISigningIdentityRepository)
            policy = await request.get(ISigningKeyPolicy)
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert isinstance(local_repo, JsonSigningIdentityRepository)
    assert isinstance(server_repo, PostgresSigningIdentityRepository)
    assert isinstance(policy, InstanceSigningKeyPolicy)


async def test__server_container__git_credentials_go_through_postgres_and_local_stays_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cryptography.fernet import Fernet  # noqa: PLC0415
    from hse_doc_studio.core.git_sync.protocols import (  # noqa: PLC0415
        ICredentialAccess,
        IGitCredentialRepository,
        IGitCredentialUsage,
        IGitRemoteBindings,
    )
    from hse_doc_studio.infra.db.repositories.git_credentials import (  # noqa: PLC0415
        PostgresCredentialAccess,
        PostgresCredentialUsage,
        PostgresGitCredentialRepository,
        PostgresGitRemoteBindings,
    )
    from hse_doc_studio.infra.git_sync.credential_access import (  # noqa: PLC0415
        DirectCredentialAccess,
        LocalGitRemoteBindings,
    )
    from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_got = [
                await request.get(IGitCredentialRepository),
                await request.get(ICredentialAccess),
                await request.get(IGitRemoteBindings),
            ]
        async with server() as request:
            server_got = [
                await request.get(IGitCredentialRepository),
                await request.get(ICredentialAccess),
                await request.get(IGitRemoteBindings),
                await request.get(IGitCredentialUsage),
            ]
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert [type(item) for item in local_got] == [
        JsonGitCredentialRepository,
        DirectCredentialAccess,
        LocalGitRemoteBindings,
    ]
    assert [type(item) for item in server_got] == [
        PostgresGitCredentialRepository,
        PostgresCredentialAccess,
        PostgresGitRemoteBindings,
        PostgresCredentialUsage,
    ]


async def test__server_container__submissions_use_postgres_and_object_archive_while_local_stays_on_volume() -> None:
    from hse_doc_studio.core.repositories import IPackSubmissionRepository  # noqa: PLC0415
    from hse_doc_studio.core.submission_archive import (  # noqa: PLC0415
        DisabledSubmissionArchive,
        ISubmissionArchive,
        ISubmissionAudit,
        NoSubmissionAudit,
    )
    from hse_doc_studio.infra.db.repositories.submission import PostgresPackSubmissionRepository  # noqa: PLC0415
    from hse_doc_studio.infra.persistence.submission import JsonPackSubmissionRepository  # noqa: PLC0415
    from hse_doc_studio.infra.submission.archive import (  # noqa: PLC0415
        AuditSubmissionDownloads,
        ObjectSubmissionArchive,
    )
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    local = create_container(StudioMode.local)
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    server = create_container(StudioMode.server, engine=engine)
    try:
        async with local() as request:
            local_got = [
                await request.get(t) for t in (IPackSubmissionRepository, ISubmissionArchive, ISubmissionAudit)
            ]
        async with server() as request:
            server_got = [
                await request.get(t) for t in (IPackSubmissionRepository, ISubmissionArchive, ISubmissionAudit)
            ]
    finally:
        await local.close()
        await server.close()
        await engine.dispose()

    assert [type(x) for x in local_got] == [JsonPackSubmissionRepository, DisabledSubmissionArchive, NoSubmissionAudit]
    assert [type(x) for x in server_got] == [
        PostgresPackSubmissionRepository,
        ObjectSubmissionArchive,
        AuditSubmissionDownloads,
    ]


async def test__server_container__relay_client_and_describer_read_personal_runner_settings() -> None:
    """Выключение личных раннеров в установке видят и ретрансляция ИИ, и состояние провайдера «через раннер»."""
    from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings  # noqa: PLC0415
    from hse_doc_studio.use_cases.ai_providers.relay_info import ProviderRelayDescriber  # noqa: PLC0415
    from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        personal = await container.get(IPersonalRunnerSettings)
        client = await container.get(AiRelayClient)
        describer = await container.get(ProviderRelayDescriber)
    finally:
        await container.close()
        await engine.dispose()

    assert client._settings is personal
    assert describer._settings is personal
