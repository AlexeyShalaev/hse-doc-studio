"""Установка раннера по SSH (docs/design/runner-install.md, раздел 5).

Порядок: probe (адрес проходит SSRF-политику, берётся только ключ хоста) -> confirm (админ подтверждает отпечаток,
Студия входит с закреплённым ключом и определяет ОС, Docker и systemd, строит план) -> install (шаги в реальном
времени, повтор возможен) -> при успехе учётные данные стираются из памяти.

Учётные данные одноразовые: живут в `SshSession` в памяти процесса и стираются при успехе, отмене и по сроку. Если
админ явно отметил «сохранить», после первого успешного входа они уходят в хранилище зашифрованными. Секреты не
попадают в журнал аудита, ответы и тексты ошибок.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import shlex
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.egress import EgressBlockedError, EgressPurpose, IEgressPolicy
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.runner_install import (
    HostKey,
    InstallError,
    InstallJob,
    InstallStepState,
    InstallTarget,
    ISshConnector,
    ISshCredentialRepository,
    ISshSession,
    RemoteSystem,
    SavedSshCredential,
    SshAuth,
    SshAuthKind,
    SshError,
    SshTarget,
)
from hse_doc_studio.core.runner_install.entities import InstallJobState
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install.common import wait_token_used
from hse_doc_studio.use_cases.runner_install.jobs import InstallJobStore
from hse_doc_studio.use_cases.runner_install.service import InstallBusyError

logger = structlog.get_logger()

SESSION_TTL = timedelta(minutes=15)
MAX_SESSIONS = 20
MAX_RUNNING_JOBS = 3
TOKEN_TTL = timedelta(hours=1)
STEPS = ("connect", "token", "docker", "service", "verify", "register")
DOCKER_INSTALL = "curl -fsSL https://get.docker.com | sh"
SERVICE_NAME = "hse-runner"
_SUPPORTED_OS = frozenset({"linux", "darwin"})


class SshSessionNotFoundError(Exception):
    """Сессия установки не найдена, истекла или принадлежит другому админу."""


class FingerprintMismatchError(Exception):
    """Подтверждённый отпечаток не совпал с тем, что показывали."""


class SshPolicyError(Exception):
    """Адрес закрыт политикой исходящих запросов (SSRF) либо не разрешился."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason


@dataclass(slots=True)
class PlanStep:
    key: str
    action: str


@dataclass(slots=True)
class SshSession:
    id: str
    created_by: str
    created_at: datetime
    target: SshTarget
    address: str
    host_key: HostKey
    auth: SshAuth | None = field(repr=False)
    save_credentials: bool = False
    label: str = ""
    credential_id: str | None = None
    touched_at: datetime = field(default_factory=utc_now)
    system: RemoteSystem | None = None
    plan: list[PlanStep] = field(default_factory=list)
    job: InstallJob | None = None
    # Установка по сохранённым данным: после отказа сессия не нужна, повторить можно новым запуском.
    one_shot: bool = False

    def wipe(self) -> None:
        self.auth = None


class SshSessionStore:
    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self._items: dict[str, SshSession] = {}

    def add(self, session: SshSession) -> None:
        self._sweep()
        while len(self._items) >= MAX_SESSIONS:
            self.remove(min(self._items.values(), key=lambda s: s.touched_at).id)
        self._items[session.id] = session

    def get(self, session_id: str, owner: str) -> SshSession:
        self._sweep()
        session = self._items.get(session_id)
        if session is None or session.created_by != owner:
            raise SshSessionNotFoundError(session_id)
        session.touched_at = self._clock()
        return session

    def remove(self, session_id: str) -> None:
        session = self._items.pop(session_id, None)
        if session is not None:
            session.wipe()

    def running_jobs(self) -> int:
        return sum(1 for s in self._items.values() if s.job is not None and s.job.state is InstallJobState.running)

    def _sweep(self) -> None:
        now = self._clock()
        for sid in [i for i, s in self._items.items() if now - s.touched_at > SESSION_TTL]:
            self.remove(sid)


def _require_admin(actor: Actor) -> str:
    if not actor.is_instance_admin or actor.id is None:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


def parse_recon(output: str) -> RemoteSystem:
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    return RemoteSystem(
        os=values.get("os", "").strip().lower(),
        arch=values.get("arch", "").strip(),
        distro=values.get("distro", "").strip(),
        has_docker=values.get("has_docker") == "1",
        docker_usable=values.get("docker_ok") == "1",
        has_systemd=values.get("systemd") == "1",
        is_root=values.get("uid") == "0",
    )


_RECON = """\
echo "os=$(uname -s)"
echo "arch=$(uname -m)"
echo "uid=$(id -u)"
if [ -r /etc/os-release ]; then (. /etc/os-release; echo "distro=${ID:-}"); fi
if command -v docker >/dev/null 2>&1; then echo has_docker=1; else echo has_docker=0; fi
if docker info >/dev/null 2>&1; then echo docker_ok=1; else echo docker_ok=0; fi
if [ -d /run/systemd/system ]; then echo systemd=1; else echo systemd=0; fi
"""


def build_plan(system: RemoteSystem, target: SshTarget) -> list[PlanStep]:
    """Шаги по найденному на хосте. `blocked` значит, что без вмешательства админа установка невозможна."""
    steps = [PlanStep("connect", "run"), PlanStep("token", "run")]
    if system.os not in _SUPPORTED_OS:
        return [*steps, PlanStep("service", "blocked")]
    if system.has_docker and (system.docker_usable or system.os == "linux"):
        steps.append(PlanStep("docker", "skip"))
    elif system.os == "linux":
        steps.append(PlanStep("docker", "install_docker"))
    else:
        steps.append(PlanStep("docker", "blocked"))
    needs_root = system.os == "linux" and not system.is_root
    steps.append(PlanStep("service", "blocked" if needs_root and not target.sudo else "run"))
    steps += [PlanStep("verify", "run"), PlanStep("register", "run")]
    return steps


class SshInstallService:
    def __init__(  # noqa: PLR0913
        self,
        registry: RunnerRegistry,
        connector: ISshConnector,
        egress: IEgressPolicy,
        sessions: SshSessionStore,
        jobs: InstallJobStore,
        audit: IAuditLog,
        uow: IUnitOfWork,
        credentials: ISshCredentialRepository | None,
        *,
        enabled: bool = True,
        image: str,
        script: Callable[[str], str],
        data_dir: str = "/var/lib/hse-runner",
        register_timeout_s: float = 180.0,
        poll_s: float = 2.0,
        verify_timeout_s: float = 30.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._registry = registry
        self._connector = connector
        self._egress = egress
        self._sessions = sessions
        self._jobs = jobs
        self._audit = audit
        self._uow = uow
        self._credentials = credentials
        self._enabled = enabled
        self._image = image
        self._script = script
        self._data_dir = data_dir
        self._register_timeout_s = register_timeout_s
        self._poll_s = poll_s
        self._verify_timeout_s = verify_timeout_s
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()

    def capability(self, actor: Actor) -> dict[str, bool]:
        _require_admin(actor)
        return {"enabled": self._enabled, "can_save_credentials": self._credentials is not None}

    # ---- 1. probe ----------------------------------------------------------------------------------------------

    async def probe(
        self, actor: Actor, target: SshTarget, auth: SshAuth, *, save_credentials: bool, label: str
    ) -> tuple[SshSession, HostKey]:
        actor_id = _require_admin(actor)
        if not self._enabled:
            raise InstallError("ssh_disabled")
        address = await self._authorize(target.host, target.port)
        try:
            host_key = await self._connector.fetch_host_key(address, target.port)
        except SshError:
            await self._audit_event("runner_install.ssh.probe_failed", actor_id, target, {"code": "unreachable"})
            raise
        session = SshSession(
            id=uuid4().hex,
            created_by=actor_id,
            created_at=self._clock(),
            target=target,
            address=address,
            host_key=host_key,
            auth=auth,
            save_credentials=save_credentials and self._credentials is not None,
            label=label.strip()[:80],
        )
        self._sessions.add(session)
        await self._audit_event(
            "runner_install.ssh.probe",
            actor_id,
            target,
            {"fingerprint": host_key.fingerprint, "key_type": host_key.key_type},
        )
        return session, host_key

    # ---- 2. confirm --------------------------------------------------------------------------------------------

    async def confirm(self, actor: Actor, session_id: str, fingerprint: str) -> SshSession:
        actor_id = _require_admin(actor)
        session = self._sessions.get(session_id, actor_id)
        if not hmac.compare_digest(fingerprint.strip().encode(), session.host_key.fingerprint.encode()):
            await self._audit_event(
                "runner_install.ssh.confirm_rejected",
                actor_id,
                session.target,
                {"fingerprint": session.host_key.fingerprint},
            )
            raise FingerprintMismatchError
        await self._audit_event(
            "runner_install.ssh.confirm", actor_id, session.target, {"fingerprint": session.host_key.fingerprint}
        )
        conn = await self._open(session)
        try:
            result = await conn.run("sh -s", stdin=_RECON, timeout=30)
        finally:
            await conn.close()
        if result.code != 0:
            raise InstallError("recon_failed", result.stderr[-300:])
        session.system = parse_recon(result.stdout)
        session.plan = build_plan(session.system, session.target)
        return session

    # ---- 3. install --------------------------------------------------------------------------------------------

    async def install(
        self, actor: Actor, session_id: str, *, studio_url: str, name: str | None, install_docker: bool
    ) -> InstallJob:
        actor_id = _require_admin(actor)
        session = self._sessions.get(session_id, actor_id)
        if session.system is None or session.auth is None:
            raise InstallError("not_confirmed")
        if session.job is not None and session.job.state is InstallJobState.running:
            raise InstallBusyError(session.id)
        if self._sessions.running_jobs() >= MAX_RUNNING_JOBS:
            raise InstallBusyError("ssh")
        blocked = next((p for p in session.plan if p.action == "blocked"), None)
        if blocked is not None:
            raise InstallError("plan_blocked", blocked.key)
        if any(p.key == "docker" and p.action == "install_docker" for p in session.plan) and not install_docker:
            raise InstallError("docker_missing")
        runner_name = self._runner_name(name, session.target)
        job = self._jobs.create(InstallTarget.ssh, runner_name, actor_id, STEPS)
        session.job = job
        await self._audit_event(
            "runner_install.ssh.start",
            actor_id,
            session.target,
            {"job": job.id, "install_docker": install_docker, "save_credentials": session.save_credentials},
        )
        self._spawn(self._execute(actor, session, job, studio_url, install_docker=install_docker, fresh=True))
        return job

    async def cancel(self, actor: Actor, session_id: str) -> None:
        actor_id = _require_admin(actor)
        session = self._sessions.get(session_id, actor_id)
        self._sessions.remove(session_id)
        await self._audit_event("runner_install.ssh.cancel", actor_id, session.target, {})

    # ---- saved credentials -------------------------------------------------------------------------------------

    async def list_credentials(self, actor: Actor) -> list[SavedSshCredential]:
        _require_admin(actor)
        return await self._credentials.list() if self._credentials is not None else []

    async def delete_credential(self, actor: Actor, credential_id: str) -> None:
        actor_id = _require_admin(actor)
        if self._credentials is None or not await self._credentials.delete(credential_id):
            raise RunnerNotFoundError(credential_id)
        async with self._uow.begin():
            await self._audit.record("runner_install.ssh.credentials_delete", actor_id=actor_id, target=credential_id)

    async def run_saved(self, actor: Actor, credential_id: str, *, action: str, studio_url: str) -> InstallJob:
        """Обновление или переустановка в один клик по сохранённым данным; ключ хоста закреплён сохранённый."""
        actor_id = _require_admin(actor)
        if self._credentials is None:
            raise RunnerNotFoundError(credential_id)
        saved = await self._credentials.get(credential_id)
        auth = await self._credentials.get_auth(credential_id)
        if saved is None or auth is None:
            raise RunnerNotFoundError(credential_id)
        if self._sessions.running_jobs() >= MAX_RUNNING_JOBS:
            raise InstallBusyError("ssh")
        target = SshTarget(saved.host, saved.port, saved.username, saved.sudo)
        address = await self._authorize(target.host, target.port)
        session = SshSession(
            id=uuid4().hex,
            created_by=actor_id,
            created_at=self._clock(),
            target=target,
            address=address,
            host_key=saved.host_key,
            auth=auth,
            credential_id=saved.id,
            one_shot=True,
        )
        self._sessions.add(session)
        job = self._jobs.create(InstallTarget.ssh, saved.runner_name or f"hse-runner-{saved.id[:6]}", actor_id, STEPS)
        session.job = job
        await self._audit_event("runner_install.ssh.run_saved", actor_id, target, {"job": job.id, "action": action})
        self._spawn(
            self._execute(
                actor, session, job, studio_url, install_docker=False, fresh=action == "reinstall", recon=True
            )
        )
        return job

    # ---- internals ---------------------------------------------------------------------------------------------

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    def _runner_name(requested: str | None, target: SshTarget) -> str:
        base = "".join(c if c.isalnum() else "-" for c in (requested or target.host).lower()).strip("-")[:30]
        return f"{base or 'hse-runner'}-{uuid4().hex[:6]}"

    async def _authorize(self, host: str, port: int) -> str:
        try:
            resolved = await self._egress.authorize(host, port, purpose=EgressPurpose.user)
        except OSError as exc:
            raise SshPolicyError("address_unresolved") from exc
        except EgressBlockedError as exc:
            raise SshPolicyError("address_blocked", exc.reason.value) from exc
        if not resolved.addresses:
            raise SshPolicyError("address_unresolved")
        return resolved.addresses[0]

    async def _open(self, session: SshSession) -> ISshSession:
        if session.auth is None:
            raise InstallError("credentials_expired")
        try:
            return await self._connector.connect(session.address, session.target, session.auth, session.host_key)
        except SshError as exc:
            raise InstallError(
                "host_key_changed" if exc.code == "host_key_mismatch" and session.credential_id else exc.code,
                exc.detail,
            ) from exc

    async def _audit_event(self, action: str, actor_id: str, target: SshTarget, details: Mapping[str, object]) -> None:
        async with self._uow.begin():
            await self._audit.record(
                action,
                actor_id=actor_id,
                target=f"{target.username}@{target.host}:{target.port}",
                details=dict(details),
            )

    def _sudo(self, session: SshSession) -> tuple[str, str]:
        """(префикс команды, строка stdin с паролем sudo). Пароль идёт первой строкой stdin, а не в аргументах."""
        system = session.system
        if system is None or system.os != "linux" or system.is_root or not session.target.sudo:
            return "", ""
        if session.auth is not None and session.auth.kind is SshAuthKind.password:
            return "sudo -S -p '' ", session.auth.secret.reveal() + "\n"
        return "sudo -n ", ""

    def _prelude(self, token: str, studio_url: str, name: str) -> str:
        env = {
            "HSE_RUNNER__API_URL": studio_url,
            "HSE_RUNNER__TOKEN": token,
            "HSE_RUNNER__NAME": name,
            "HSE_RUNNER_IMAGE": self._image,
        }
        return "".join(f"{k}={shlex.quote(v)}; export {k}\n" for k, v in env.items())

    async def _execute(  # noqa: PLR0913, PLR0915, C901
        self,
        actor: Actor,
        session: SshSession,
        job: InstallJob,
        studio_url: str,
        *,
        install_docker: bool,
        fresh: bool,
        recon: bool = False,
    ) -> None:
        conn: ISshSession | None = None
        token_id: str | None = None
        secret = ""
        step = self._jobs.set_step
        try:
            step(job, "connect", InstallStepState.running)
            conn = await self._open(session)
            if recon or session.system is None:
                result = await conn.run("sh -s", stdin=_RECON, timeout=30)
                session.system = parse_recon(result.stdout)
                session.plan = build_plan(session.system, session.target)
                blocked = next((p for p in session.plan if p.action == "blocked"), None)
                if blocked is not None:
                    raise InstallError("plan_blocked", blocked.key)
            step(
                job,
                "connect",
                InstallStepState.done,
                session.system.distro or session.system.os if session.system else "",
            )
            await self._save_credentials(actor, session, job)

            step(job, "token", InstallStepState.running)
            created = await self._registry.create_registration_token(
                actor, label=f"ssh {job.name}", ttl=TOKEN_TTL, max_uses=1
            )
            token_id, secret = created.token.id, created.secret
            step(job, "token", InstallStepState.done)

            sudo, sudo_stdin = self._sudo(session)
            await self._ensure_docker(conn, session, job, sudo, sudo_stdin, install_docker=install_docker)
            await self._install_service(conn, session, job, sudo, sudo_stdin, secret, studio_url, fresh=fresh)
            await self._verify(conn, job)
            if fresh:
                step(job, "register", InstallStepState.running)
                await wait_token_used(
                    self._registry, actor, token_id, timeout_s=self._register_timeout_s, poll_s=self._poll_s
                )
                step(job, "register", InstallStepState.done)
            else:
                step(job, "register", InstallStepState.skipped)
                await self._revoke(actor, token_id)
            job.state = InstallJobState.succeeded
            await self._audit_event("runner_install.ssh.succeeded", actor.id or "", session.target, {"job": job.id})
            if session.credential_id and self._credentials is not None:
                await self._credentials.mark_used(session.credential_id, self._clock(), job.name)
            self._sessions.remove(session.id)
        except (InstallError, SshError) as exc:
            detail = (exc.detail or "").replace(secret, "***") if secret else (exc.detail or "")
            await self._fail(actor, session, job, token_id, exc.code, detail)
        except Exception:
            logger.exception("ssh_install_failed", job=job.id)
            await self._fail(actor, session, job, token_id, "unexpected", "")
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    await conn.close()

    async def _ensure_docker(  # noqa: PLR0913
        self,
        conn: ISshSession,
        session: SshSession,
        job: InstallJob,
        sudo: str,
        sudo_stdin: str,
        *,
        install_docker: bool,
    ) -> None:
        action = next((p.action for p in session.plan if p.key == "docker"), "skip")
        if action == "skip":
            self._jobs.set_step(job, "docker", InstallStepState.skipped, "present")
            return
        if action != "install_docker" or not install_docker:
            raise InstallError("docker_missing")
        self._jobs.set_step(job, "docker", InstallStepState.running)
        done = await conn.run(f"{sudo}sh -c {shlex.quote(DOCKER_INSTALL)}", stdin=sudo_stdin or None, timeout=900)
        if done.code != 0:
            raise InstallError("docker_install_failed", (done.stderr or done.stdout)[-400:])
        self._jobs.set_step(job, "docker", InstallStepState.done)

    async def _install_service(  # noqa: PLR0913
        self,
        conn: ISshSession,
        session: SshSession,
        job: InstallJob,
        sudo: str,
        sudo_stdin: str,
        token: str,
        studio_url: str,
        *,
        fresh: bool,
    ) -> None:
        self._jobs.set_step(job, "service", InstallStepState.running)
        script = self._script(self._image)
        if fresh and session.credential_id:
            purge = await conn.run(
                f"{sudo}sh -s -- uninstall --purge",
                stdin=sudo_stdin + self._prelude(token, studio_url, job.name) + script,
                timeout=300,
            )
            if purge.code != 0:
                raise InstallError("service_uninstall_failed", (purge.stderr or purge.stdout)[-400:])
        stdin = sudo_stdin + self._prelude(token, studio_url, job.name) + script
        done = await conn.run(f"{sudo}sh -s -- install", stdin=stdin, timeout=900)
        if done.code != 0:
            raise InstallError("service_install_failed", (done.stderr or done.stdout)[-400:])
        self._jobs.set_step(job, "service", InstallStepState.done)

    async def _verify(self, conn: ISshSession, job: InstallJob) -> None:
        self._jobs.set_step(job, "verify", InstallStepState.running)
        waited = 0.0
        command = f"systemctl is-active {SERVICE_NAME} 2>/dev/null || launchctl list 2>/dev/null | grep -q hse-runner"
        while True:
            done = await conn.run(command, timeout=20)
            if done.code == 0:
                break
            if waited >= self._verify_timeout_s:
                raise InstallError("service_not_active")
            await asyncio.sleep(self._poll_s)
            waited += self._poll_s
        self._jobs.set_step(job, "verify", InstallStepState.done)

    async def _save_credentials(self, actor: Actor, session: SshSession, job: InstallJob) -> None:
        if not session.save_credentials or session.credential_id or session.auth is None or self._credentials is None:
            return
        saved = SavedSshCredential(
            id=uuid4().hex,
            label=session.label or f"{session.target.username}@{session.target.host}",
            host=session.target.host,
            port=session.target.port,
            username=session.target.username,
            sudo=session.target.sudo,
            auth_kind=session.auth.kind,
            host_key=session.host_key,
            created_by=actor.id or "",
            created_at=self._clock(),
            runner_name=job.name,
        )
        async with self._uow.begin():
            await self._credentials.add(saved, session.auth)
            await self._audit.record(
                "runner_install.ssh.credentials_save",
                actor_id=actor.id,
                target=saved.id,
                details={
                    "host": saved.host,
                    "port": saved.port,
                    "username": saved.username,
                    "auth": saved.auth_kind.value,
                },
            )
        session.credential_id = saved.id

    async def _revoke(self, actor: Actor, token_id: str | None) -> None:
        if token_id is not None:
            with contextlib.suppress(RunnerNotFoundError):
                await self._registry.revoke_registration_token(actor, token_id)

    async def _fail(
        self, actor: Actor, session: SshSession, job: InstallJob, token_id: str | None, code: str, detail: str
    ) -> None:
        for step in job.steps:
            if step.state is InstallStepState.running:
                step.state = InstallStepState.failed
                step.detail = detail[:400]
        job.state = InstallJobState.failed
        job.error_code = code
        job.error_detail = detail[:400]
        await self._revoke(actor, token_id)
        await self._audit_event(
            "runner_install.ssh.failed", actor.id or "", session.target, {"job": job.id, "code": code}
        )
        if session.one_shot:
            self._sessions.remove(session.id)
