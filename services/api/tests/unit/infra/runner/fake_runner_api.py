"""Минимальный сервер протокола раннера для тестов клиента и цикла: тела проверяются строгими схемами контракта."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from hse_doc_studio.api.schemas import runner as schemas

TOKEN = "registration-secret"  # noqa: S105 — токен регистрации: годится только для register
RUNNER_TOKEN = "hsrn_runner-secret"  # noqa: S105 — токен раннера из ответа register
_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"


def envelope_body(kind: str = "compile", *, attempt: int = 1, job_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = copy.deepcopy(json.loads((_FIXTURES / "JobEnvelopeBody" / f"{kind}.json").read_text()))
    body["attempt"] = attempt
    if job_id is not None:
        body["spec"]["id"] = job_id
    return body


@dataclass
class FakeJob:
    envelope: dict[str, Any]
    cancel: bool = False
    stale: bool = False
    heartbeats: int = 0
    log_batches: dict[int, list[str]] = field(default_factory=dict)
    completed: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, bytes] = field(default_factory=dict)
    announced: list[dict[str, Any]] = field(default_factory=list)
    relay_body: bytes = b""
    relay_batches: list[dict[str, Any]] = field(default_factory=list)
    relay_cancel: bool = False

    @property
    def job_id(self) -> str:
        return str(self.envelope["spec"]["id"])

    @property
    def log_lines(self) -> list[str]:
        return [line for seq in sorted(self.log_batches) for line in self.log_batches[seq]]


class FakeRunnerState:
    def __init__(self) -> None:
        self.queue: list[FakeJob] = []
        self.jobs: dict[str, FakeJob] = {}
        self.registrations: list[dict[str, Any]] = []
        self.polls = 0
        self.headers_seen: list[dict[str, str]] = []
        self.fail_register_with: int | None = None
        self.blobs: dict[str, bytes] = {}
        self.blob_requests: list[tuple[str, str]] = []
        # Сервер с /announce (протокол 1.1); False: старый сервер отвечает 404.
        self.supports_announce = True
        self.announce_paused = False
        self.announces: list[dict[str, Any]] = []
        self.poll_bodies: list[dict[str, Any]] = []
        self.offline_calls = 0
        self.deregister_calls = 0
        self.pair_polls: list[str] = []
        self.pair_status = "pending"

    def enqueue(self, envelope: dict[str, Any]) -> FakeJob:
        job = FakeJob(envelope)
        self.queue.append(job)
        self.jobs[job.job_id] = job
        return job


def _error(status: int, code: str, detail: str = "x") -> JSONResponse:
    return JSONResponse({"detail": detail, "code": code}, status_code=status)


def create_fake_app(state: FakeRunnerState) -> FastAPI:  # noqa: C901
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next: Any) -> Response:
        state.headers_seen.append(dict(request.headers))
        if "/pair/" in request.url.path:
            return await call_next(request)
        expected = TOKEN if request.url.path.endswith("/register") else RUNNER_TOKEN
        if request.headers.get("authorization") != f"Bearer {expected}":
            return _error(401, "runner_unauthorized")
        return await call_next(request)

    @app.post("/api/runner/v1/register")
    async def register(body: schemas.RunnerRegisterRequestBody) -> Any:
        if state.fail_register_with is not None:
            return _error(state.fail_register_with, "runner_disabled")
        state.registrations.append(body.model_dump())
        return schemas.RunnerRegisterResponseBody(
            runner_id="runner-1", runner_token=RUNNER_TOKEN, lease_s=45, heartbeat_s=10, max_poll_wait_s=25
        ).model_dump()

    @app.post("/api/runner/v1/announce")
    async def announce_runner(body: schemas.RunnerAnnounceRequestBody) -> Any:
        if not state.supports_announce:
            return Response(status_code=404)
        state.announces.append(body.model_dump())
        return schemas.RunnerAnnounceResponseBody(
            runner_id="runner-1",
            server_features=sorted(set(body.features) & {"announce", "offline", "ai_slots", "ai_relay"}),
            owner_kind="user",
            paused=state.announce_paused,
            relay_keepalive_s=2,
        ).model_dump()

    @app.post("/api/runner/v1/offline")
    async def offline() -> Any:
        if not state.supports_announce:
            return Response(status_code=404)
        state.offline_calls += 1
        return Response(status_code=204)

    @app.post("/api/runner/v1/deregister")
    async def deregister() -> Any:
        state.deregister_calls += 1
        return Response(status_code=204)

    @app.post("/api/runner/v1/pair/start")
    async def pair_start(body: schemas.RunnerPairStartRequestBody) -> Any:
        return json.loads((_FIXTURES / "RunnerPairStartResponseBody" / "default.json").read_text())

    @app.post("/api/runner/v1/pair/poll")
    async def pair_poll(body: schemas.RunnerPairPollRequestBody) -> Any:
        state.pair_polls.append(body.device_code)
        token = TOKEN if state.pair_status == "approved" else None
        return {"status": state.pair_status, "registration_token": token}

    @app.get("/api/runner/v1/jobs/{job_id}/relay/request")
    async def relay_request(job_id: str) -> Any:
        job = state.jobs.get(job_id)
        if job is None:
            return _error(404, "relay_request_gone")
        digest = hashlib.sha256(job.relay_body).hexdigest()
        return Response(content=job.relay_body, headers={"X-Relay-Sha256": digest})

    @app.post("/api/runner/v1/jobs/{job_id}/relay/events")
    async def relay_events(job_id: str, body: schemas.RelayEventBatchBody) -> Any:
        job = job_or_error(job_id, body.attempt)
        if isinstance(job, JSONResponse):
            return job
        job.relay_batches.append(body.model_dump())
        return {"cancel": job.relay_cancel}

    @app.post("/api/runner/v1/poll")
    async def poll(request: Request) -> Any:
        raw = await request.json()
        state.poll_bodies.append(raw)
        schemas.PollRequestBody.model_validate(raw)
        if not state.supports_announce and "free_ai_slots" in raw:
            return _error(422, "unknown_field")
        state.polls += 1
        for job in list(state.queue):
            relay = job.envelope["spec"]["kind"] == "ai.relay"
            if (relay and raw.get("free_ai_slots", 0) > 0) or (not relay and raw["free_slots"] > 0):
                state.queue.remove(job)
                return {"envelope": job.envelope}
        await asyncio.sleep(0.02)
        return {"envelope": None}

    def job_or_error(job_id: str, attempt: int) -> FakeJob | JSONResponse:
        job = state.jobs.get(job_id)
        if job is None:
            return _error(404, "job_not_found")
        if job.stale or attempt != job.envelope["attempt"]:
            return _error(409, "stale_attempt")
        return job

    @app.post("/api/runner/v1/jobs/{job_id}/heartbeat")
    async def heartbeat(job_id: str, body: schemas.HeartbeatRequestBody) -> Any:
        job = job_or_error(job_id, body.attempt)
        if isinstance(job, JSONResponse):
            return job
        job.heartbeats += 1
        return {"cancel": job.cancel, "lease_until": "2026-10-26T09:31:00+00:00"}

    @app.post("/api/runner/v1/jobs/{job_id}/log")
    async def log(job_id: str, body: schemas.LogBatchBody) -> Any:
        job = job_or_error(job_id, body.attempt)
        if isinstance(job, JSONResponse):
            return job
        job.log_batches.setdefault(body.seq, list(body.lines))
        return Response(status_code=204)

    @app.get("/api/runner/v1/jobs/{job_id}/blobs/{sha256}")
    async def get_blob(job_id: str, sha256: str, request: Request) -> Any:
        state.blob_requests.append((job_id, request.headers.get("x-job-token", "")))
        data = state.blobs.get(sha256)
        if data is None:
            return _error(404, "blob_missing")
        return Response(content=data, media_type="application/octet-stream")

    @app.post("/api/runner/v1/jobs/{job_id}/artifacts")
    async def announce(job_id: str, body: schemas.ArtifactUploadRequestBody) -> Any:
        job = job_or_error(job_id, body.attempt)
        if isinstance(job, JSONResponse):
            return job
        job.announced.append(body.artifact.model_dump())
        return {"url": None}

    @app.put("/api/runner/v1/jobs/{job_id}/artifacts/{sha256}")
    async def put_artifact(job_id: str, sha256: str, request: Request) -> Any:
        state.jobs[job_id].artifacts[sha256] = await request.body()
        return Response(status_code=204)

    @app.post("/api/runner/v1/jobs/{job_id}/complete")
    async def complete(job_id: str, body: schemas.CompleteRequestBody) -> Any:
        job = job_or_error(job_id, body.attempt)
        if isinstance(job, JSONResponse):
            return job
        job.completed.append(body.model_dump(mode="json"))
        return {"accepted": True}

    return app


class SwitchTransport(httpx.AsyncBaseTransport):
    """ASGI-транспорт с рубильником: пока `down`, соединение рвётся, как при остановленном api."""

    def __init__(self, app: FastAPI) -> None:
        self._inner = httpx.ASGITransport(app=app)
        self.down = False
        self.failures = 0
        self.fail_next: int = 0
        self.status_next: int = 0
        self.status_calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.down or self.fail_next > 0:
            self.fail_next = max(0, self.fail_next - 1)
            self.failures += 1
            raise httpx.ConnectError("api is down", request=request)
        if self.status_next > 0:
            self.status_next -= 1
            self.status_calls += 1
            return httpx.Response(503, request=request)
        return await self._inner.handle_async_request(request)
