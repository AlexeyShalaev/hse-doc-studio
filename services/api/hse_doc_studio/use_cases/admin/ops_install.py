"""Название и адрес установки, настройки сборки: чтение с учётом окружения и правка админом."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.identity.instance_settings import (
    ARTIFACT_RETENTION_RANGE,
    BUILD_KEYS,
    BUILD_TIMEOUT_RANGE,
    INSTANCE_KEYS,
    KEY_ARTIFACT_RETENTION_DAYS,
    KEY_BUILD_TIMEOUT_S,
    KEY_DOCS_URL,
    KEY_NAME,
    KEY_PERSONAL_ENABLED,
    KEY_PERSONAL_MAX_PER_USER,
    KEY_PERSONAL_WAIT_S,
    KEY_PUBLIC_URL,
    NAME_MAX,
    PERSONAL_MAX_PER_USER_RANGE,
    PERSONAL_RUNNER_KEYS,
    PERSONAL_WAIT_RANGE,
    BuildSettings,
    InstanceEnvOverrides,
    InstanceSettings,
    effective_build_settings,
    effective_instance_settings,
    effective_personal_runner_settings,
    is_valid_url,
)
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.setting_source import SettingDescription, describe_setting
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.core.jobs.routing import PersonalRunnerSettings, RouteReason
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN
from hse_doc_studio.use_cases.jobs.personal_settings import InstancePersonalRunnerSettings
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService


@dataclass(frozen=True)
class InstanceView:
    settings: InstanceSettings
    descriptions: dict[str, SettingDescription]


@dataclass(frozen=True)
class BuildView:
    settings: BuildSettings
    descriptions: dict[str, SettingDescription]
    personal: PersonalRunnerSettings = PersonalRunnerSettings()


@dataclass(frozen=True)
class InstancePatch:
    """Меняется только заданное (не None). Пустой `docs_url` убирает ссылку."""

    name: str | None = None
    public_url: str | None = None
    docs_url: str | None = None


@dataclass(frozen=True)
class BuildPatch:
    timeout_s: int | None = None
    artifact_retention_days: int | None = None
    personal_runners_enabled: bool | None = None
    personal_runner_wait_s: int | None = None
    personal_runners_max_per_user: int | None = None


def _invalid() -> IdentityError:
    return IdentityError(IdentityErrorCode.input_invalid)


def _text_value(raw: str, limit: int) -> str:
    value = " ".join(raw.split())
    if not value or len(value) > limit:
        raise _invalid()
    return value


def _instance_changes(patch: InstancePatch) -> tuple[dict[str, str], list[str]]:
    """Что записать и что сбросить; негодное значение отвергает весь запрос."""
    values: dict[str, str] = {}
    cleared: list[str] = []
    if patch.name is not None:
        values[KEY_NAME] = _text_value(patch.name, NAME_MAX)
    if patch.public_url is not None:
        url = patch.public_url.strip()
        if not is_valid_url(url, secure_only=True):
            raise _invalid()
        values[KEY_PUBLIC_URL] = url
    if patch.docs_url is not None:
        docs = patch.docs_url.strip()
        if not docs:
            cleared.append(KEY_DOCS_URL)
        elif is_valid_url(docs, secure_only=False):
            values[KEY_DOCS_URL] = docs
        else:
            raise _invalid()
    return values, cleared


def _check_locked(keys: set[str], env: InstanceEnvOverrides) -> None:
    """Заданный окружением ключ не правится: отказ целиком, ничего не записывается."""
    if locked := sorted(keys & env.locked_keys()):
        raise IdentityError(
            IdentityErrorCode.setting_locked, f"{message_for(IdentityErrorCode.setting_locked)} ({', '.join(locked)})"
        )


class GetInstanceSettingsUC:
    def __init__(self, repo: IInstanceSettingsRepository, env: InstanceEnvOverrides) -> None:
        self._repo = repo
        self._env = env

    async def instance(self, actor: Actor) -> InstanceView:
        require_admin(actor)
        stored = await self._repo.get_all()
        return InstanceView(
            effective_instance_settings(stored, self._env),
            {k: describe_setting(k, stored=stored, locked=self._env.locked_keys()) for k in INSTANCE_KEYS},
        )

    async def build(self, actor: Actor) -> BuildView:
        require_admin(actor)
        stored = await self._repo.get_all()
        return BuildView(
            effective_build_settings(stored, self._env),
            {
                k: describe_setting(k, stored=stored, locked=self._env.locked_keys())
                for k in (*BUILD_KEYS, *PERSONAL_RUNNER_KEYS)
            },
            effective_personal_runner_settings(stored, self._env),
        )


class UpdateInstanceSettingsUC:
    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        audit: IAuditLog,
        uow: IUnitOfWork,
        read: GetInstanceSettingsUC,
    ) -> None:
        self._repo = repo
        self._env = env
        self._audit = audit
        self._uow = uow
        self._read = read

    async def execute(self, actor: Actor, patch: InstancePatch) -> InstanceView:
        admin_id = require_admin(actor)
        values, cleared = _instance_changes(patch)
        _check_locked({*values, *cleared}, self._env)
        if values or cleared:
            async with self._uow.begin():
                for key, value in values.items():
                    await self._repo.set(key, value, source=SOURCE_ADMIN)
                for key in cleared:
                    await self._repo.delete(key)
                await self._audit.record(
                    "settings.instance_update", actor_id=admin_id, details={**values, **dict.fromkeys(cleared, None)}
                )
        return await self._read.instance(actor)


def _build_values(patch: BuildPatch) -> dict[str, int | bool]:
    """Что записать; значение вне диапазона отвергает весь запрос."""
    values: dict[str, int | bool] = {}
    for key, value, (low, high) in (
        (KEY_BUILD_TIMEOUT_S, patch.timeout_s, BUILD_TIMEOUT_RANGE),
        (KEY_ARTIFACT_RETENTION_DAYS, patch.artifact_retention_days, ARTIFACT_RETENTION_RANGE),
        (KEY_PERSONAL_WAIT_S, patch.personal_runner_wait_s, PERSONAL_WAIT_RANGE),
        (KEY_PERSONAL_MAX_PER_USER, patch.personal_runners_max_per_user, PERSONAL_MAX_PER_USER_RANGE),
    ):
        if value is None:
            continue
        if not low <= value <= high:
            raise _invalid()
        values[key] = value
    if patch.personal_runners_enabled is not None:
        values[KEY_PERSONAL_ENABLED] = patch.personal_runners_enabled
    return values


class UpdateBuildSettingsUC:
    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        audit: IAuditLog,
        uow: IUnitOfWork,
        read: GetInstanceSettingsUC,
        *,
        personal: InstancePersonalRunnerSettings | None = None,
        queue: JobQueueService | None = None,
    ) -> None:
        self._repo = repo
        self._env = env
        self._audit = audit
        self._uow = uow
        self._read = read
        self._personal = personal
        self._queue = queue

    async def execute(self, actor: Actor, patch: BuildPatch) -> BuildView:
        admin_id = require_admin(actor)
        values = _build_values(patch)
        _check_locked(set(values), self._env)
        before = (await self._read.build(actor)).personal
        if values:
            build = {k: v for k, v in values.items() if k not in PERSONAL_RUNNER_KEYS}
            personal = {k: v for k, v in values.items() if k in PERSONAL_RUNNER_KEYS}
            async with self._uow.begin():
                for key, value in values.items():
                    await self._repo.set(key, value, source=SOURCE_ADMIN)
                if build:
                    await self._audit.record("settings.build_update", actor_id=admin_id, details=build)
                if personal:
                    await self._audit.record("settings.personal_runners_update", actor_id=admin_id, details=personal)
            if self._personal is not None:
                self._personal.invalidate()
        view = await self._read.build(actor)
        if before.enabled and not view.personal.enabled:
            await self._personal_runners_turned_off()
        return view

    async def _personal_runners_turned_off(self) -> None:
        """Ждущие личный раннер сборки сразу идут на общие, ждущие ретрансляции отменяются."""
        if self._queue is None:
            return
        await self._queue.expire_personal_wait(reason=RouteReason.disabled)
        await self._queue.cancel_pinned(runner_id=None, error_code=RelayErrorCode.relay_unavailable.value)
