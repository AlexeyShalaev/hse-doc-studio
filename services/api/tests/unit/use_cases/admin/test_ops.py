"""Админка эксплуатации: квоты, политика подписи, место, сервисы, очередь и общие ИИ-провайдеры."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.egress import EgressBlockedError, EgressBlockReason, EgressPurpose, EgressTarget
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.jobs.admin import JobAdminFilter
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource, QuotaSettings
from hse_doc_studio.core.signatures.key_policy import ServerKeyPolicy
from hse_doc_studio.use_cases.admin.ops_ai_providers import (
    CheckInstanceAiProviderUC,
    CreateInstanceAiProviderUC,
    DeleteInstanceAiProviderUC,
    InstanceAiProviderInput,
    InstanceAiProviderPatch,
    InstanceAiProviderStore,
    ListInstanceAiProvidersUC,
    UpdateInstanceAiProviderUC,
)
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, ListQueueUC
from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, QuotaService, UpdateQuotasUC
from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.job_quotas import InMemoryQuotaOverrides
from tests.fakes.ops import CountingStorageReader, InMemoryJobAdminReader, NoopUow, ReversingCipher

ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
STUDENT = Actor(kind=ActorKind.user, id="anna")


async def _audit_actions(audit: InMemoryAuditLog) -> list[str]:
    return [e.action for e in reversed(await audit.list())]


def _not_found(exc: pytest.ExceptionInfo[IdentityError]) -> bool:
    return exc.value.code is IdentityErrorCode.not_found


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test__quotas__update_then_read__roundtrip_and_audit() -> None:
    repo = InMemoryInstanceSettingsRepository()
    audit = InMemoryAuditLog()
    service = QuotaService(repo)
    update = UpdateQuotasUC(repo, audit, NoopUow(), service)

    saved = await update.execute(ADMIN, QuotaSettings(user_concurrent=2, max_duration_s=300))

    assert await GetQuotasUC(repo).execute(ADMIN) == saved
    assert await _audit_actions(audit) == ["settings.quotas_update"]
    # Повтор того же значения журнал не засоряет.
    await update.execute(ADMIN, saved)
    assert await _audit_actions(audit) == ["settings.quotas_update"]


async def test__quotas__null_removes_limit() -> None:
    repo = InMemoryInstanceSettingsRepository()
    update = UpdateQuotasUC(repo, InMemoryAuditLog(), NoopUow(), QuotaService(repo))
    await update.execute(ADMIN, QuotaSettings(user_concurrent=2))

    await update.execute(ADMIN, QuotaSettings())

    assert await GetQuotasUC(repo).execute(ADMIN) == QuotaSettings()
    assert "jobs.concurrent" not in await repo.get_all()


async def test__quota_service__caches_for_ttl_and_forgets_on_update() -> None:
    repo = InMemoryInstanceSettingsRepository()
    clock = _Clock()
    service = QuotaService(repo, ttl_s=5, monotonic=clock)
    update = UpdateQuotasUC(repo, InMemoryAuditLog(), NoopUow(), service)
    assert await service.current() is None

    await repo.set("jobs.concurrent", 3, source="admin")
    assert await service.current() is None
    clock.now = 6
    quota = await service.current()
    assert quota is not None
    assert quota.max_running_per_user == 3

    await update.execute(ADMIN, QuotaSettings(user_concurrent=1))
    quota = await service.current()
    assert quota is not None
    assert quota.max_running_per_user == 1


async def test__signing_policy__defaults_to_forbidden_and_audits_change() -> None:
    repo = InMemoryInstanceSettingsRepository()
    audit = InMemoryAuditLog()
    assert await GetSigningPolicyUC(repo).execute(ADMIN) is ServerKeyPolicy.forbidden

    update = UpdateSigningPolicyUC(repo, audit, NoopUow())
    await update.execute(ADMIN, ServerKeyPolicy.allowed)
    await update.execute(ADMIN, ServerKeyPolicy.allowed)

    assert await GetSigningPolicyUC(repo).execute(ADMIN) is ServerKeyPolicy.allowed
    assert await _audit_actions(audit) == ["settings.signing_policy_update"]


async def test__storage_usage__cached_until_ttl_or_refresh() -> None:
    reader = CountingStorageReader()
    clock = _Clock()
    uc = GetStorageUsageUC(reader, ttl_s=60, monotonic=clock)

    first = await uc.execute(ADMIN)
    assert (await uc.execute(ADMIN)) is first
    assert reader.reads == 1
    clock.now = 61
    assert (await uc.execute(ADMIN)).blob_count == 2
    assert (await uc.execute(ADMIN, refresh=True)).blob_count == 3


async def test__ops_use_cases__not_admin__not_found() -> None:
    repo = InMemoryInstanceSettingsRepository()
    queue = InMemoryJobQueue()
    calls = [
        GetQuotasUC(repo).execute(STUDENT),
        UpdateQuotasUC(repo, InMemoryAuditLog(), NoopUow(), QuotaService(repo)).execute(STUDENT, QuotaSettings()),
        GetSigningPolicyUC(repo).execute(STUDENT),
        UpdateSigningPolicyUC(repo, InMemoryAuditLog(), NoopUow()).execute(STUDENT, ServerKeyPolicy.allowed),
        GetStorageUsageUC(CountingStorageReader()).execute(STUDENT),
        ListQueueUC(InMemoryJobAdminReader(queue)).execute(STUDENT, JobAdminFilter()),
        ListInstanceAiProvidersUC(InstanceAiProviderStore(repo, ReversingCipher())).execute(STUDENT),
    ]
    for call in calls:
        with pytest.raises(IdentityError) as exc:
            await call
        assert _not_found(exc)


def _enqueue_request(user: object, **kwargs: object) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=user,  # type: ignore[arg-type]
        tags=frozenset({"tex"}),
        payload={},
        **kwargs,  # type: ignore[arg-type]
    )


async def test__queue__filters_and_pages_newest_first() -> None:
    queue = InMemoryJobQueue()
    anna, boris = uuid4(), uuid4()
    for user in (anna, boris, anna, anna):
        await queue.enqueue(_enqueue_request(user))
    uc = ListQueueUC(InMemoryJobAdminReader(queue))

    only_anna = await uc.execute(ADMIN, JobAdminFilter(user_id=anna), limit=2)
    rest = await uc.execute(ADMIN, JobAdminFilter(user_id=anna), before_seq=only_anna.next_before_seq, limit=2)

    assert len(only_anna.items) == 2
    assert only_anna.next_before_seq is not None
    assert len(rest.items) == 1
    assert rest.next_before_seq is None
    assert all(j.user_id == anna for j in (*only_anna.items, *rest.items))
    assert (await uc.execute(ADMIN, JobAdminFilter(state=JobState.running))).items == ()


async def test__cancel_job__queued__cancelled_and_audited_terminal__left_alone() -> None:
    queue = InMemoryJobQueue()
    audit = InMemoryAuditLog()
    uc = CancelJobUC(queue, JobQueueService(queue), audit, NoopUow())
    job = (await queue.enqueue(_enqueue_request(uuid4()))).job

    cancelled = await uc.execute(ADMIN, job.id)
    again = await uc.execute(ADMIN, job.id)

    assert cancelled.state is JobState.cancelled
    assert again.state is JobState.cancelled
    assert await _audit_actions(audit) == ["queue.job_cancel"]


async def test__cancel_job__unknown__not_found_and_not_admin_hidden() -> None:
    from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError  # noqa: PLC0415

    queue = InMemoryJobQueue()
    uc = CancelJobUC(queue, JobQueueService(queue), InMemoryAuditLog(), NoopUow())

    with pytest.raises(QueuedJobNotFoundError):
        await uc.execute(ADMIN, uuid4())
    with pytest.raises(IdentityError):
        await uc.execute(STUDENT, uuid4())


class _Egress:
    """Закрывает всё, что называется `internal-only`; остальное разрешает."""

    def __init__(self) -> None:
        self.purposes: list[EgressPurpose] = []

    async def authorize(self, host: str, port: int | None = None, *, purpose: EgressPurpose = EgressPurpose.user):  # type: ignore[no-untyped-def]
        self.purposes.append(purpose)
        if host == "metadata.google.internal":
            raise EgressBlockedError(host, EgressBlockReason.metadata_host)
        return EgressTarget(host=host, port=port, addresses=("10.0.0.5",))


class _Lister:
    def __init__(self, fail: bool = False) -> None:
        self.seen: list[AIProvider] = []
        self._fail = fail

    async def list_models(self, provider: AIProvider) -> list[str]:
        self.seen.append(provider)
        if self._fail:
            raise ConnectionError("secret-host.internal refused")
        return ["m1", "m2"]


def _providers() -> tuple[InstanceAiProviderStore, InMemoryInstanceSettingsRepository, InMemoryAuditLog, _Egress]:
    repo = InMemoryInstanceSettingsRepository()
    return InstanceAiProviderStore(repo, ReversingCipher()), repo, InMemoryAuditLog(), _Egress()


async def test__ai_providers__create__key_stored_encrypted_and_never_listed() -> None:
    store, repo, audit, egress = _providers()
    create = CreateInstanceAiProviderUC(store, audit, NoopUow(), egress)

    created = await create.execute(
        ADMIN, InstanceAiProviderInput(name=" Ollama ", type=AIProviderType.openai_compat, api_key="sk-live-123")
    )

    assert created.name == "Ollama"
    assert created.key_set is True
    assert "sk-live-123" not in str(await repo.get_all())
    assert "sk-live-123" not in (await repo.get_secret(f"ai_provider_key/{created.id}") or "")
    listed = await ListInstanceAiProvidersUC(store).execute(ADMIN)
    assert [p.id for p in listed] == [created.id]
    assert "sk-live-123" not in repr(listed)
    assert await _audit_actions(audit) == ["settings.ai_provider_create"]
    assert "sk-live-123" not in str([e.details for e in await audit.list()])


async def test__ai_providers__bad_input__rejected_without_writes() -> None:
    store, repo, audit, egress = _providers()
    create = CreateInstanceAiProviderUC(store, audit, NoopUow(), egress)
    cases = [
        InstanceAiProviderInput(name="", type=AIProviderType.openai, api_key="k"),
        InstanceAiProviderInput(name="x", type=AIProviderType.openai, api_key=""),
        InstanceAiProviderInput(name="x", type=AIProviderType.openai, api_key="k", base_url="ftp://host"),
        InstanceAiProviderInput(name="x", type=AIProviderType.openai, api_key="k", base_url="http://u:p@host"),
        InstanceAiProviderInput(
            name="x", type=AIProviderType.openai, api_key="k", base_url="http://metadata.google.internal/v1"
        ),
        InstanceAiProviderInput(name="x", type=AIProviderType.openai, api_key="k", connect_timeout_s=0),
    ]
    for case in cases:
        with pytest.raises(IdentityError) as exc:
            await create.execute(ADMIN, case)
        assert exc.value.code is IdentityErrorCode.input_invalid

    assert await repo.get_all() == {}
    assert await audit.list() == []


async def test__ai_providers__base_url__checked_with_admin_purpose() -> None:
    store, _, audit, egress = _providers()
    create = CreateInstanceAiProviderUC(store, audit, NoopUow(), egress)

    await create.execute(
        ADMIN,
        InstanceAiProviderInput(name="LAN", type=AIProviderType.ollama, base_url="http://10.0.0.5:11434"),
    )

    assert egress.purposes == [EgressPurpose.admin]


async def test__ai_providers__update__blank_key_keeps_and_clear_removes() -> None:
    store, repo, audit, egress = _providers()
    created = await CreateInstanceAiProviderUC(store, audit, NoopUow(), egress).execute(
        ADMIN, InstanceAiProviderInput(name="P", type=AIProviderType.claude, api_key="sk-1")
    )
    update = UpdateInstanceAiProviderUC(store, audit, NoopUow(), egress)

    renamed = await update.execute(ADMIN, created.id, InstanceAiProviderPatch(name="Q", api_key=""))
    assert (renamed.name, renamed.key_set) == ("Q", True)
    assert await store.reveal_key(created.id) == "sk-1"

    rotated = await update.execute(ADMIN, created.id, InstanceAiProviderPatch(api_key="sk-2"))
    assert rotated.key_set is True
    assert await store.reveal_key(created.id) == "sk-2"

    cleared = await update.execute(ADMIN, created.id, InstanceAiProviderPatch(clear_key=True))
    assert cleared.key_set is False
    assert await repo.get_secret(f"ai_provider_key/{created.id}") is None
    assert (await store.get(created.id)).key_set is False  # type: ignore[union-attr]


async def test__ai_providers__delete_and_missing() -> None:
    store, repo, audit, egress = _providers()
    created = await CreateInstanceAiProviderUC(store, audit, NoopUow(), egress).execute(
        ADMIN, InstanceAiProviderInput(name="P", type=AIProviderType.claude, api_key="sk-1")
    )
    delete = DeleteInstanceAiProviderUC(store, audit, NoopUow())

    await delete.execute(ADMIN, created.id)

    assert await repo.get_all() == {}
    with pytest.raises(IdentityError) as exc:
        await delete.execute(ADMIN, created.id)
    assert _not_found(exc)
    assert await _audit_actions(audit) == ["settings.ai_provider_create", "settings.ai_provider_delete"]


async def test__ai_providers__check__passes_key_to_lister_and_hides_failure_details() -> None:
    store, _, audit, egress = _providers()
    created = await CreateInstanceAiProviderUC(store, audit, NoopUow(), egress).execute(
        ADMIN, InstanceAiProviderInput(name="P", type=AIProviderType.claude, api_key="sk-1")
    )
    lister = _Lister()

    ok = await CheckInstanceAiProviderUC(store, lister).execute(ADMIN, created.id)
    failed = await CheckInstanceAiProviderUC(store, _Lister(fail=True)).execute(ADMIN, created.id)

    assert (ok.ok, ok.models) == (True, ("m1", "m2"))
    assert lister.seen[0].api_key == "sk-1"
    assert failed.ok is False
    assert failed.error == "ConnectionError"
    assert "secret-host" not in str(failed)


async def test__services_overview__probes_runners_and_smtp() -> None:
    from hse_doc_studio.core.jobs.runners import Runner  # noqa: PLC0415
    from hse_doc_studio.use_cases.admin.ops_services import ServicesOverviewUC, ServiceState  # noqa: PLC0415
    from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService  # noqa: PLC0415

    from tests.fakes.runners import InMemoryRunnerRepository  # noqa: PLC0415

    now = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    runners = InMemoryRunnerRepository()
    smtp = SmtpSettingsService(InMemoryInstanceSettingsRepository(), ReversingCipher())  # type: ignore[arg-type]
    uc = ServicesOverviewUC(runners, smtp, clock=lambda: now)

    def by_id(items):  # type: ignore[no-untyped-def]
        return {i.id: i for i in items}

    empty = by_id(await uc.execute(ADMIN, {"database": None, "s3": "timeout"}))
    assert empty["database"].state is ServiceState.ok
    assert (empty["s3"].state, empty["s3"].reason) == (ServiceState.down, "timeout")
    assert empty["languagetool"].state is ServiceState.not_configured
    assert empty["runners"].state is ServiceState.not_configured
    assert empty["smtp"].state is ServiceState.not_configured

    def runner(runner_id: str, seen: datetime) -> Runner:
        return Runner(
            id=runner_id,
            name=runner_id,
            token_hash=runner_id,
            tags=frozenset(),
            concurrency=1,
            resource_class="standard",
            version="1",
            created_at=now - timedelta(days=1),
            last_seen_at=seen,
        )

    await runners.add(runner("old", now - timedelta(hours=1)))
    stale = by_id(await uc.execute(ADMIN, {}))
    assert (stale["runners"].state, stale["runners"].reason) == (ServiceState.down, "no_online_runner")
    await runners.add(runner("fresh", now))
    live = by_id(await uc.execute(ADMIN, {}))
    assert (live["runners"].state, live["runners"].total, live["runners"].online) == (ServiceState.ok, 2, 1)


async def test__quota_service__overrides_reach_the_queue_and_duration() -> None:
    user, org = uuid4(), uuid4()
    repo = InMemoryInstanceSettingsRepository()
    await repo.set("jobs.concurrent", 3, source="admin")
    await repo.set("jobs.max_duration_s", 300, source="admin")
    overrides = InMemoryQuotaOverrides(
        QuotaOverride(QuotaOwnerKind.user, str(user), QuotaResource.concurrent_user, 1),
        QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.max_duration_s, 90),
    )
    service = QuotaService(repo, overrides, ttl_s=0)

    quota = await service.current()

    assert quota is not None
    assert quota.user_cap(user, None) == 1
    assert quota.user_cap(uuid4(), None) == 3
    assert await service.max_duration_s(uuid4(), org) == 90.0
    assert await service.max_duration_s(uuid4(), None) == 300.0


async def test__quota_service__only_overrides__still_limits() -> None:
    user = uuid4()
    overrides = InMemoryQuotaOverrides(QuotaOverride(QuotaOwnerKind.user, str(user), QuotaResource.concurrent_user, 2))
    service = QuotaService(InMemoryInstanceSettingsRepository(), overrides, ttl_s=0)

    quota = await service.current()

    assert quota is not None
    assert quota.user_caps == {user: 2}
    assert await service.max_duration_s(user, None) is None
