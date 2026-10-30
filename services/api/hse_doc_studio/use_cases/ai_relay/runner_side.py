"""Ручки раннера для ретрансляции ИИ: забрать тело запроса и отдать порции ответа модели.

Каждый вызов проходит ту же проверку, что лог и выходы: токен задачи, аренда этим раннером, номер попытки.
Тело отдаётся только задаче `ai.relay` этого раннера; чужой токен неотличим от отсутствующей задачи.
"""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError
from hse_doc_studio.core.jobs.relay import IRelayHub, RelayRequestGoneError
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.jobs.wire import RelayEventAck, RelayEventBatch
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore, StoredRelayRequest
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService


class RelayRunnerService:
    def __init__(self, io: RunnerJobIoService, store: RelayRequestStore, hub: IRelayHub) -> None:
        self._io = io
        self._store = store
        self._hub = hub

    async def request_body(self, runner: Runner, job_id: UUID, job_token: str) -> StoredRelayRequest:
        job = await self._io.authorize(runner, job_id, job_token)
        if job.kind is not JobKind.ai_relay:
            raise QueuedJobNotFoundError(f"job {job_id} is not a relay job")
        stored = self._store.get(job_id)
        if stored is None or stored.runner_id != runner.id:
            raise RelayRequestGoneError(f"relay request of job {job_id} is gone")
        self._hub.mark_picked(job_id)
        return stored

    async def push_events(self, runner: Runner, job_id: UUID, job_token: str, batch: RelayEventBatch) -> RelayEventAck:
        """Порция по порядку; `cancel` при уходе потребителя или отмене задачи в очереди."""
        job = await self._io.authorize(runner, job_id, job_token, batch.attempt)
        if job.kind is not JobKind.ai_relay:
            raise QueuedJobNotFoundError(f"job {job_id} is not a relay job")
        cancel = await self._hub.push(job_id, batch.seq, batch.events)
        return RelayEventAck(cancel=cancel or job.cancel_requested)
