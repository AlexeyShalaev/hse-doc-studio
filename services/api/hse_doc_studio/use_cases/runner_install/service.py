"""Установка раннера на этой же машине: токен регистрации, шаги хоста, ожидание регистрации, аудит без секретов.

Здесь же обновление поставленного отсюда раннера на месте (новый образ и манифест, тот же токен, том и запись в Студии,
откат на прежнюю версию при неудаче) и удаление установки вместе с отзывом её раннера.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from uuid import uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.runner_install import (
    Capability,
    ILocalRunnerHost,
    InstallError,
    InstallJob,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
    PreviousRelease,
    ResourceOverrides,
    UpgradeError,
)
from hse_doc_studio.core.runner_install.entities import InstallJobState, InstallStep
from hse_doc_studio.core.runner_isolation import installed_runner
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
# Шаг отката появляется в задаче обновления, только когда откатывать есть что.
ROLLBACK_STEP = "rollback"


class InstallUnavailableError(Exception):
    """Способ установки здесь невозможен; `reason` объясняет, почему."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InstallBusyError(Exception):
    """Установка этим способом уже идёт."""


def install_token_label(name: str) -> str:
    """Название токена регистрации, который установка выдаёт раннеру `name`: по нему удаление находит этот токен."""
    return f"install {name}"


def _image_tag(image: str) -> str:
    """Тег образа как версия: у `registry/x:0.15.0` это `0.15.0`; без тега пусто."""
    tail = image.rsplit("/", 1)[-1]
    return tail.rpartition(":")[2] if ":" in tail and "@" not in tail else ""


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
        version: str = "",
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
        # Версия Студии: её образ ставят установка и обновление. По умолчанию это тег образа.
        self._version = version or image.rpartition(":")[2]
        self._data_dir = data_dir.rstrip("/")
        self._internal_urls = dict(internal_urls or {})
        self._register_timeout_s = register_timeout_s
        self._poll_s = poll_s
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def version(self) -> str:
        return self._version

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
        """Поставленное отсюда, каждое со своей записью раннера в Студии, если она нашлась (по поду или по имени)."""
        _require_admin(actor)
        found: list[LocalInstance] = []
        for host in self._hosts.values():
            if (await host.capability()).available:
                found.extend(await host.list_instances())
        if not found:
            return found
        runners = await self._instance_runners(actor)
        matched: list[LocalInstance] = []
        for item in found:
            runner = installed_runner(item.name, runners)
            matched.append(
                replace(item, runner_id=runner.id, runner_version=runner.version) if runner is not None else item
            )
        return matched

    async def _instance_runners(self, actor: Actor) -> list[Runner]:
        return await self._registry.list_runners(actor, owner_kind=RunnerOwnerKind.instance)

    async def remove(self, actor: Actor, target: InstallTarget, name: str) -> None:
        """Удалить установку из админки и отозвать её раннер тем же use case, что «Отозвать раннер».

        Порядок: проверка, что установка есть; отзыв её токена регистрации, если он ещё действует; отзыв раннера;
        удаление Deployment или контейнера; аудит. Отзыв идёт до удаления, чтобы ни на миг не было раннера, который
        работает без установки (под Deployment после удаления ещё до 10 минут доделывает сборки). Если удаление на
        хосте сорвалось, раннер уже отозван, а установка осталась в «Установках без раннера»: её можно удалить снова,
        повтор отзывать уже нечего. Отзыв не удался: на хосте ничего не тронуто, повтор начнёт сначала.
        """
        actor_id = _require_admin(actor)
        host = self._hosts.get(target)
        if host is None or name not in {i.name for i in await host.list_instances()}:
            raise RunnerNotFoundError(name)
        running = self._jobs.running(target)
        if running is not None and running.name == name:
            raise InstallBusyError(target.value)
        tokens = await self._revoke_install_tokens(actor, name)
        runner = installed_runner(name, await self._instance_runners(actor))
        if runner is not None:
            with contextlib.suppress(RunnerNotFoundError):
                await self._registry.revoke(actor, runner.id)
        details: dict[str, object] = {"target": target.value, "revoked_runner": runner.id if runner else None}
        if tokens:
            details["revoked_registrations"] = tokens
        try:
            removed = await host.remove(name)
        except InstallError as exc:
            failed = {**details, "code": exc.code}
            await self._remove_record("runner_install.local.remove_failed", actor_id, name, failed)
            raise
        if not removed:
            raise RunnerNotFoundError(name)
        await self._remove_record("runner_install.local.remove", actor_id, name, details)

    async def _revoke_install_tokens(self, actor: Actor, name: str) -> list[str]:
        """Токены регистрации этой установки, которыми ещё можно зарегистрироваться: после удаления они не нужны."""
        now = utc_now()
        label = install_token_label(name)
        revoked: list[str] = []
        for token in await self._registry.list_registration_tokens(actor):
            if token.label == label and token.usable(now):
                with contextlib.suppress(RunnerNotFoundError):
                    await self._registry.revoke_registration_token(actor, token.id)
                    revoked.append(token.id)
        return revoked

    async def _remove_record(self, action: str, actor_id: str, name: str, details: Mapping[str, object]) -> None:
        async with self._uow.begin():
            await self._audit.record(action, actor_id=actor_id, target=name, details=dict(details))

    async def start_upgrade(self, actor: Actor, target: InstallTarget, name: str) -> InstallJob:
        """Обновить поставленный отсюда раннер на месте до версии Студии; токен новый не выпускается.

        Разрешено и на той же версии: манифест применяется заново по нынешним правилам. Блокировка общая с установкой
        этим способом (`InstallBusyError`): два изменения одного хоста одновременно не идут.
        """
        actor_id = _require_admin(actor)
        host = self._hosts.get(target)
        if host is None:
            raise InstallUnavailableError("disabled")
        capability = await host.capability()
        if not capability.available:
            raise InstallUnavailableError(capability.reason.value if capability.reason else "disabled")
        if name not in {i.name for i in await host.list_instances()}:
            raise RunnerNotFoundError(name)
        if self._jobs.running(target) is not None:
            raise InstallBusyError(target.value)
        runner = installed_runner(name, await self._instance_runners(actor))
        job = self._jobs.create(target, name, actor_id, (*host.upgrade_steps(), "reconnect"))
        details: dict[str, object] = {
            "target": target.value,
            "from_version": runner.version if runner is not None else None,
            "to_version": self._version,
        }
        if runner is not None:
            details["runner"] = runner.id
        await self._record("runner_install.local.upgrade", actor_id, job, details)
        task = asyncio.create_task(self._run_upgrade(actor, host, job, runner))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run_upgrade(self, actor: Actor, host: ILocalRunnerHost, job: InstallJob, runner: Runner | None) -> None:
        actor_id = actor.id or ""
        before = runner.version if runner is not None else None
        previous: PreviousRelease | None = None
        try:

            async def report(key: str, state: InstallStepState, detail: str) -> None:
                self._jobs.set_step(job, key, state, detail)

            outcome = await host.upgrade(job.name, self._image, report)
            previous = outcome.previous
            restarted = utc_now()
            after = await self._wait_reconnected(job, actor, runner, restarted)
            # Дальше обновление удалось: сбой записи итога не повод возвращать прежнюю версию.
            previous = None
            job.state = InstallJobState.succeeded
            await self._record(
                "runner_install.local.upgrade_succeeded",
                actor_id,
                job,
                {
                    "target": job.target.value,
                    "from_version": before,
                    "to_version": after,
                    "from_image": outcome.old_image,
                    "to_image": outcome.new_image,
                },
            )
        except InstallError as exc:
            if isinstance(exc, UpgradeError):
                previous = exc.previous
            await self._fail_upgrade(actor, host, job, runner, previous, exc.code, exc.detail)
        except Exception:
            logger.exception("runner_upgrade_failed", job=job.id, target=job.target.value)
            await self._fail_upgrade(actor, host, job, runner, previous, "unexpected", "")

    async def _wait_reconnected(
        self, job: InstallJob, actor: Actor, runner: Runner | None, since: datetime
    ) -> str | None:
        """Раннер снова на связи и сообщил версию Студии; без записи в Студии ждать некого, шаг пропускается.

        Старый процесс к этому времени уже остановлен (Recreate в кластере, `docker stop` рядом), поэтому сигнал позже
        `since` с нужной версией идёт от нового.
        """
        if runner is None:
            self._jobs.set_step(job, "reconnect", InstallStepState.skipped, "no_runner")
            return None
        self._jobs.set_step(job, "reconnect", InstallStepState.running)
        outcome, seen_version = await self._await_version(actor, runner.id, self._version, since)
        if outcome == "revoked":
            raise InstallError("runner_revoked")
        if outcome == "timeout":
            raise InstallError("reconnect_timeout", seen_version)
        self._jobs.set_step(job, "reconnect", InstallStepState.done, seen_version)
        return seen_version

    async def _await_version(self, actor: Actor, runner_id: str, version: str, since: datetime) -> tuple[str, str]:
        """Ждать сигнала раннера позже `since` с версией `version` (не дольше шага «снова на связи»).

        Итог: (`ok`, версия), (`revoked`, ``) или (`timeout`, последняя замеченная версия).
        """
        seen_version = ""
        waited = 0.0
        while waited < self._register_timeout_s:
            current = next((r for r in await self._instance_runners(actor) if r.id == runner_id), None)
            if current is None or current.revoked_at is not None:
                return "revoked", ""
            if current.last_seen_at is not None and current.last_seen_at >= since:
                seen_version = current.version
                if current.version == version:
                    return "ok", current.version
            await asyncio.sleep(self._poll_s)
            waited += self._poll_s
        return "timeout", seen_version

    async def _fail_upgrade(  # noqa: PLR0913
        self,
        actor: Actor,
        host: ILocalRunnerHost,
        job: InstallJob,
        runner: Runner | None,
        previous: PreviousRelease | None,
        code: str,
        detail: str,
    ) -> None:
        """Обновление не удалось: если установку уже заменили, вернуть прежнюю версию отдельным шагом, затем итог."""
        before = runner.version if runner is not None else None
        for step in job.steps:
            if step.state is InstallStepState.running:
                step.state = InstallStepState.failed
                step.detail = detail[:400]
        job.error_code = code
        job.error_detail = detail[:400]
        details: dict[str, object] = {
            "target": job.target.value,
            "code": code,
            "from_version": before,
            "to_version": self._version,
            "rolled_back": False,
        }
        if previous is not None:
            await self._rollback(actor, host, job, runner, previous)
            details["rolled_back"] = bool(job.rolled_back)
            if job.rollback_error is not None:
                details["rollback_error"] = job.rollback_error
            if job.rollback_reconnected is not None:
                details["rollback_reconnected"] = job.rollback_reconnected
        job.state = InstallJobState.failed
        await self._record("runner_install.local.upgrade_failed", actor.id or "", job, details)

    async def _rollback(
        self, actor: Actor, host: ILocalRunnerHost, job: InstallJob, runner: Runner | None, previous: PreviousRelease
    ) -> None:
        """Шаг «Откат на прежнюю версию»: хост возвращает прежний Deployment или контейнер и ждёт, что он поднялся,
        затем Студия ждёт, что раннер вышел на связь с прежней версией (как шаг «снова на связи»).

        Не вышел: откат состоялся (`rolled_back`), но шаг помечен ошибкой и `rollback_reconnected` ложно.
        """
        before = runner.version if runner is not None else None
        job.steps.append(InstallStep(ROLLBACK_STEP))
        self._jobs.set_step(job, ROLLBACK_STEP, InstallStepState.running, previous.image)
        version = before or _image_tag(previous.image)
        started = utc_now()
        try:
            await host.rollback(job.name, previous)
        except InstallError as exc:
            job.rolled_back, job.rollback_error = False, exc.code
            self._jobs.set_step(job, ROLLBACK_STEP, InstallStepState.failed, exc.detail[:400])
            return
        except Exception:
            logger.exception("runner_rollback_failed", job=job.id, target=job.target.value)
            job.rolled_back, job.rollback_error = False, "unexpected"
            self._jobs.set_step(job, ROLLBACK_STEP, InstallStepState.failed, "")
            return
        job.rolled_back, job.rollback_version = True, version
        if runner is None or not before:
            self._jobs.set_step(job, ROLLBACK_STEP, InstallStepState.done, version)
            return
        outcome, _ = await self._await_version(actor, runner.id, before, started)
        job.rollback_reconnected = outcome == "ok"
        state = InstallStepState.done if job.rollback_reconnected else InstallStepState.failed
        self._jobs.set_step(job, ROLLBACK_STEP, state, version)

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
                actor, label=install_token_label(job.name), ttl=TOKEN_TTL, max_uses=1
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
