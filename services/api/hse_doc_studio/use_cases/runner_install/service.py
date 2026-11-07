"""Установка раннера на этой же машине: токен регистрации, шаги хоста, ожидание регистрации, аудит без секретов."""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Mapping
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.runner_install import (
    Capability,
    ILocalRunnerHost,
    InstallError,
    InstallJob,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
    ResourceOverrides,
)
from hse_doc_studio.core.runner_install.entities import InstallJobState
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install.common import wait_token_used
from hse_doc_studio.use_cases.runner_install.jobs import InstallJobStore

logger = structlog.get_logger()

TOKEN_TTL = timedelta(hours=1)
REGISTER_TIMEOUT_S = 180.0
REGISTER_POLL_S = 2.0
_NAME_SAFE = re.compile(r"[^a-z0-9-]+")
MAX_CONCURRENCY = 8


class InstallUnavailableError(Exception):
    """Способ установки здесь невозможен; `reason` объясняет, почему."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InstallBusyError(Exception):
    """Установка этим способом уже идёт."""


def _require_admin(actor: Actor) -> str:
    if not actor.is_instance_admin or actor.id is None:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


class RunnerInstallService:
    def __init__(  # noqa: PLR0913
        self,
        registry: RunnerRegistry,
        hosts: Mapping[InstallTarget, ILocalRunnerHost],
        jobs: InstallJobStore,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        image: str,
        data_dir: str,
        internal_urls: Mapping[InstallTarget, str] | None = None,
        register_timeout_s: float = REGISTER_TIMEOUT_S,
        poll_s: float = REGISTER_POLL_S,
    ) -> None:
        self._registry = registry
        self._hosts = hosts
        self._jobs = jobs
        self._audit = audit
        self._uow = uow
        self._image = image
        self._data_dir = data_dir.rstrip("/")
        self._internal_urls = dict(internal_urls or {})
        self._register_timeout_s = register_timeout_s
        self._poll_s = poll_s
        self._tasks: set[asyncio.Task[None]] = set()

    async def capabilities(self, actor: Actor) -> dict[InstallTarget, Capability]:
        _require_admin(actor)
        return {target: await host.capability() for target, host in self._hosts.items()}

    async def start(
        self,
        actor: Actor,
        target: InstallTarget,
        *,
        studio_url: str,
        name: str | None,
        concurrency: int,
        resources: ResourceOverrides | None = None,
    ) -> InstallJob:
        actor_id = _require_admin(actor)
        host = self._hosts.get(target)
        if host is None:
            raise InstallUnavailableError("disabled")
        capability = await host.capability()
        if not capability.available:
            raise InstallUnavailableError(capability.reason.value if capability.reason else "disabled")
        # Границы проверяет хост до токена и задачи: вне границ установка не начинается (InvalidResourcesError).
        host.check_resources(resources)
        if self._jobs.running(target) is not None:
            raise InstallBusyError(target.value)
        runner_name = self._runner_name(name)
        job = self._jobs.create(target, runner_name, actor_id, ("token", *host.steps(), "register"))
        details: dict[str, object] = {"target": target.value}
        if resources is not None and not resources.is_empty():
            details["resources"] = {k: v for k, v in asdict(resources).items() if v}
        await self._record("runner_install.local.start", actor_id, job, details)
        task = asyncio.create_task(
            self._run(actor, host, job, studio_url, max(1, min(concurrency, MAX_CONCURRENCY)), resources)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def job(self, actor: Actor, job_id: str) -> InstallJob | None:
        _require_admin(actor)
        return self._jobs.get(job_id)

    async def instances(self, actor: Actor) -> list[LocalInstance]:
        _require_admin(actor)
        found: list[LocalInstance] = []
        for host in self._hosts.values():
            if (await host.capability()).available:
                found.extend(await host.list_instances())
        return found

    async def remove(self, actor: Actor, target: InstallTarget, name: str) -> None:
        actor_id = _require_admin(actor)
        host = self._hosts.get(target)
        if host is None or not await host.remove(name):
            raise RunnerNotFoundError(name)
        async with self._uow.begin():
            await self._audit.record(
                "runner_install.local.remove", actor_id=actor_id, target=name, details={"target": target.value}
            )

    @staticmethod
    def _runner_name(requested: str | None) -> str:
        """Имя без неожиданностей для docker и kubernetes: строчные латинские буквы, цифры и дефис, плюс суффикс."""
        base = _NAME_SAFE.sub("-", (requested or "").lower()).strip("-")[:30] or "hse-runner"
        return f"{base}-{uuid4().hex[:6]}"

    async def _record(self, action: str, actor_id: str, job: InstallJob, details: Mapping[str, object]) -> None:
        async with self._uow.begin():
            await self._audit.record(action, actor_id=actor_id, target=job.name, details={"job": job.id, **details})

    async def _run(
        self,
        actor: Actor,
        host: ILocalRunnerHost,
        job: InstallJob,
        studio_url: str,
        concurrency: int,
        resources: ResourceOverrides | None = None,
    ) -> None:
        actor_id = actor.id or ""
        token_id: str | None = None
        secret = ""
        try:
            self._jobs.set_step(job, "token", InstallStepState.running)
            created = await self._registry.create_registration_token(
                actor, label=f"install {job.name}", ttl=TOKEN_TTL, max_uses=1
            )
            token_id, secret = created.token.id, created.secret
            self._jobs.set_step(job, "token", InstallStepState.done)

            async def report(key: str, state: InstallStepState, detail: str) -> None:
                self._jobs.set_step(job, key, state, detail)

            spec = LocalRunnerSpec(
                name=job.name,
                image=self._image,
                api_url=self._internal_urls.get(job.target) or studio_url,
                data_dir=f"{self._data_dir}/{job.name}",
                concurrency=concurrency,
                token=secret,
                resources=resources,
            )
            await host.install(spec, report)
            await self._wait_registered(job, actor, token_id)
            job.state = InstallJobState.succeeded
            await self._record("runner_install.local.succeeded", actor_id, job, {"target": job.target.value})
        except InstallError as exc:
            await self._fail(
                actor, job, token_id, exc.code, exc.detail.replace(secret, "***") if secret else exc.detail
            )
        except Exception:
            logger.exception("runner_install_failed", job=job.id, target=job.target.value)
            await self._fail(actor, job, token_id, "unexpected", "")

    async def _wait_registered(self, job: InstallJob, actor: Actor, token_id: str) -> None:
        self._jobs.set_step(job, "register", InstallStepState.running)
        await wait_token_used(self._registry, actor, token_id, timeout_s=self._register_timeout_s, poll_s=self._poll_s)
        self._jobs.set_step(job, "register", InstallStepState.done)

    async def _fail(self, actor: Actor, job: InstallJob, token_id: str | None, code: str, detail: str) -> None:
        for step in job.steps:
            if step.state is InstallStepState.running:
                step.state = InstallStepState.failed
                step.detail = detail[:400]
        job.state = InstallJobState.failed
        job.error_code = code
        job.error_detail = detail[:400]
        if token_id is not None:
            with contextlib.suppress(RunnerNotFoundError):
                await self._registry.revoke_registration_token(actor, token_id)
        await self._record(
            "runner_install.local.failed", actor.id or "", job, {"target": job.target.value, "code": code}
        )
