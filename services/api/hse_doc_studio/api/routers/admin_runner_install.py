"""`/api/admin/runner-install`: поставить раннер на этой же машине (docker рядом или Deployment в кластере)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from hse_doc_studio.api.rate_limit import enforce
from hse_doc_studio.api.runner_commands import studio_base_url
from hse_doc_studio.api.schemas.runner_install import (
    CapabilityInfo,
    HostKeyInfo,
    InstallJobInfo,
    InstallStepInfo,
    LocalCapabilitiesResponse,
    LocalInstanceInfo,
    LocalTargetName,
    PlanStepInfo,
    RemoteSystemInfo,
    SavedCredentialInfo,
    SshCapabilityResponse,
    SshConfirmRequest,
    SshInstallRequest,
    SshPlanResponse,
    SshProbeRequest,
    SshProbeResponse,
    SshRunSavedRequest,
    StartLocalInstallRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.rate_limit import SSH_ATTEMPT, SSH_ATTEMPT_HOST
from hse_doc_studio.core.runner_install import (
    Capability,
    InstallError,
    InstallJob,
    InstallTarget,
    LocalInstance,
    RemoteSystem,
    SavedSshCredential,
    SshAuth,
    SshAuthKind,
    SshError,
    SshTarget,
    UnavailableReason,
)
from hse_doc_studio.use_cases.runner_install import (
    FingerprintMismatchError,
    InstallBusyError,
    InstallUnavailableError,
    RunnerInstallService,
    SshInstallService,
    SshPolicyError,
    SshSessionNotFoundError,
)
from hse_doc_studio.use_cases.runner_install.ssh_service import SESSION_TTL

router = APIRouter(prefix="/runner-install")

_NO_STORE = {"Cache-Control": "no-store"}


async def _service(request: Request) -> RunnerInstallService:
    return await request.state.dishka_container.get(RunnerInstallService)


def _capability(value: Capability) -> CapabilityInfo:
    return CapabilityInfo(available=value.available, reason=value.reason.value if value.reason else None)


def job_info(job: InstallJob) -> InstallJobInfo:
    return InstallJobInfo(
        id=job.id,
        target=job.target.value,
        name=job.name,
        state=job.state.value,
        steps=[InstallStepInfo(key=s.key, state=s.state.value, detail=s.detail) for s in job.steps],
        error_code=job.error_code,
        error_detail=job.error_detail,
        created_at=job.created_at,
    )


def _instance(item: LocalInstance) -> LocalInstanceInfo:
    return LocalInstanceInfo(
        target=item.target.value,
        name=item.name,
        image=item.image,
        state=item.state,
        created_at=item.created_at,
    )


@router.get("/local", response_model=LocalCapabilitiesResponse)
async def local_capabilities(request: Request, response: Response) -> LocalCapabilitiesResponse:
    """Где здесь можно поставить раннер; причина недоступности объясняет, почему кнопки нет."""
    response.headers.update(_NO_STORE)
    found = await (await _service(request)).capabilities(require_actor())
    no_host = Capability.no(UnavailableReason.disabled)
    return LocalCapabilitiesResponse(
        docker=_capability(found.get(InstallTarget.docker, no_host)),
        kubernetes=_capability(found.get(InstallTarget.kubernetes, no_host)),
    )


@router.get("/local/instances", response_model=list[LocalInstanceInfo])
async def local_instances(request: Request, response: Response) -> list[LocalInstanceInfo]:
    response.headers.update(_NO_STORE)
    return [_instance(i) for i in await (await _service(request)).instances(require_actor())]


@router.post("/local/{target}", response_model=InstallJobInfo, status_code=status.HTTP_202_ACCEPTED)
async def start_local_install(
    target: LocalTargetName, body: StartLocalInstallRequest, request: Request, response: Response
) -> InstallJobInfo:
    response.headers.update(_NO_STORE)
    try:
        job = await (await _service(request)).start(
            require_actor(),
            InstallTarget(target),
            studio_url=studio_base_url(request),
            name=body.name or None,
            concurrency=body.concurrency,
        )
    except InstallUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "install_unavailable", "reason": exc.reason}
        ) from exc
    except InstallBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "install_busy"}) from exc
    return job_info(job)


@router.delete("/local/{target}/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_local_instance(target: LocalTargetName, name: str, request: Request) -> Response:
    try:
        await (await _service(request)).remove(require_actor(), InstallTarget(target), name)
    except RunnerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}", response_model=InstallJobInfo)
async def install_job(job_id: str, request: Request, response: Response) -> InstallJobInfo:
    response.headers.update(_NO_STORE)
    job = (await _service(request)).job(require_actor(), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return job_info(job)


# ---- SSH ----

ssh_router = APIRouter(prefix="/runner-install/ssh")


def _remote(system: RemoteSystem) -> RemoteSystemInfo:
    return RemoteSystemInfo(
        os=system.os,
        arch=system.arch,
        distro=system.distro,
        has_docker=system.has_docker,
        docker_usable=system.docker_usable,
        has_systemd=system.has_systemd,
        is_root=system.is_root,
    )


async def _ssh(request: Request) -> SshInstallService:
    return await request.state.dishka_container.get(SshInstallService)


def _saved(item: SavedSshCredential) -> SavedCredentialInfo:
    return SavedCredentialInfo(
        id=item.id,
        label=item.label,
        host=item.host,
        port=item.port,
        username=item.username,
        sudo=item.sudo,
        auth_kind=item.auth_kind.value,
        key_type=item.host_key.key_type,
        fingerprint=item.host_key.fingerprint,
        created_at=item.created_at,
        last_used_at=item.last_used_at,
        runner_name=item.runner_name,
    )


def _auth_of(body: SshProbeRequest) -> SshAuth:
    if body.auth_kind == "password":
        if not body.password:
            raise HTTPException(status_code=422, detail={"code": "input_invalid", "field": "password"})
        return SshAuth(SshAuthKind.password, Secret(body.password))
    if not body.private_key:
        raise HTTPException(status_code=422, detail={"code": "input_invalid", "field": "private_key"})
    return SshAuth(SshAuthKind.key, Secret(body.private_key), Secret(body.passphrase) if body.passphrase else None)


def _ssh_failure(exc: Exception) -> HTTPException:
    """Понятный отказ для интерфейса; в нём нет ни секретов, ни внутренних подробностей, кроме кода причины."""
    if isinstance(exc, SshPolicyError):
        return HTTPException(422, {"code": exc.code, "reason": exc.reason})
    if isinstance(exc, SshSessionNotFoundError):
        return HTTPException(404, "Not Found")
    if isinstance(exc, FingerprintMismatchError):
        return HTTPException(409, {"code": "fingerprint_mismatch"})
    if isinstance(exc, InstallBusyError):
        return HTTPException(409, {"code": "install_busy"})
    if isinstance(exc, (SshError, InstallError)):
        return HTTPException(422, {"code": exc.code})
    raise exc


@ssh_router.get("", response_model=SshCapabilityResponse)
async def ssh_capability(request: Request, response: Response) -> SshCapabilityResponse:
    response.headers.update(_NO_STORE)
    service = await _ssh(request)
    return SshCapabilityResponse(**service.capability(require_actor()))


@ssh_router.post("/probe", response_model=SshProbeResponse, status_code=status.HTTP_201_CREATED)
async def ssh_probe(body: SshProbeRequest, request: Request, response: Response) -> SshProbeResponse:
    """Адрес проверяется политикой SSRF, затем берётся только ключ хоста; учётные данные ещё не используются."""
    response.headers.update(_NO_STORE)
    actor = require_actor()
    await enforce(request, SSH_ATTEMPT, f"user:{actor.id}")
    await enforce(request, SSH_ATTEMPT_HOST, f"host:{body.host.lower()}:{body.port}")
    auth = _auth_of(body)
    target = SshTarget(body.host.strip(), body.port, body.username, body.sudo)
    try:
        session, host_key = await (await _ssh(request)).probe(
            actor, target, auth, save_credentials=body.save_credentials, label=body.label
        )
    except (SshPolicyError, SshError, InstallError) as exc:
        raise _ssh_failure(exc) from exc
    return SshProbeResponse(
        session_id=session.id,
        host_key=HostKeyInfo(key_type=host_key.key_type, fingerprint=host_key.fingerprint),
        expires_in_s=int(SESSION_TTL.total_seconds()),
    )


@ssh_router.post("/{session_id}/confirm", response_model=SshPlanResponse)
async def ssh_confirm(
    session_id: str, body: SshConfirmRequest, request: Request, response: Response
) -> SshPlanResponse:
    response.headers.update(_NO_STORE)
    actor = require_actor()
    await enforce(request, SSH_ATTEMPT, f"user:{actor.id}")
    try:
        session = await (await _ssh(request)).confirm(actor, session_id, body.fingerprint)
    except (SshSessionNotFoundError, FingerprintMismatchError, SshError, InstallError, SshPolicyError) as exc:
        raise _ssh_failure(exc) from exc
    assert session.system is not None  # noqa: S101 — confirm всегда определяет систему
    return SshPlanResponse(
        session_id=session.id,
        system=_remote(session.system),
        plan=[PlanStepInfo(key=p.key, action=p.action) for p in session.plan],
    )


@ssh_router.post("/{session_id}/install", response_model=InstallJobInfo, status_code=status.HTTP_202_ACCEPTED)
async def ssh_install(session_id: str, body: SshInstallRequest, request: Request, response: Response) -> InstallJobInfo:
    response.headers.update(_NO_STORE)
    try:
        job = await (await _ssh(request)).install(
            require_actor(),
            session_id,
            studio_url=studio_base_url(request),
            name=body.name or None,
            install_docker=body.install_docker,
        )
    except (SshSessionNotFoundError, InstallBusyError, InstallError) as exc:
        raise _ssh_failure(exc) from exc
    return job_info(job)


@ssh_router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def ssh_delete_credential(credential_id: str, request: Request) -> Response:
    try:
        await (await _ssh(request)).delete_credential(require_actor(), credential_id)
    except RunnerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@ssh_router.get("/credentials", response_model=list[SavedCredentialInfo])
async def ssh_list_credentials(request: Request, response: Response) -> list[SavedCredentialInfo]:
    response.headers.update(_NO_STORE)
    return [_saved(c) for c in await (await _ssh(request)).list_credentials(require_actor())]


@ssh_router.post(
    "/credentials/{credential_id}/run", response_model=InstallJobInfo, status_code=status.HTTP_202_ACCEPTED
)
async def ssh_run_saved(
    credential_id: str, body: SshRunSavedRequest, request: Request, response: Response
) -> InstallJobInfo:
    """Обновление или переустановка в один клик по сохранённым данным; ключ хоста закреплён сохранённый."""
    response.headers.update(_NO_STORE)
    actor = require_actor()
    await enforce(request, SSH_ATTEMPT, f"user:{actor.id}")
    try:
        job = await (await _ssh(request)).run_saved(
            actor, credential_id, action=body.action, studio_url=studio_base_url(request)
        )
    except RunnerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc
    except (SshPolicyError, InstallBusyError, InstallError, SshError) as exc:
        raise _ssh_failure(exc) from exc
    return job_info(job)


@ssh_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def ssh_cancel(session_id: str, request: Request) -> Response:
    try:
        (await _ssh(request)).cancel(require_actor(), session_id)
    except SshSessionNotFoundError as exc:
        raise _ssh_failure(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
