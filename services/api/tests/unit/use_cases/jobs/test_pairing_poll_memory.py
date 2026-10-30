"""Память ограничителя опроса сопряжения: брошенные сопряжения не копятся до рестарта api."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from hse_doc_studio.core.jobs.pairing import PAIRING_TTL, PairingStatus, RunnerPairing
from hse_doc_studio.core.jobs.runners import RunnerHostKind
from hse_doc_studio.use_cases.jobs.pairing import RunnerPairingService

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


class _Pairings:
    """Каждый код устройства находит своё ожидающее сопряжение (как после `pair/start`)."""

    async def get_by_device_hash(self, device_hash: str) -> RunnerPairing:
        return RunnerPairing(
            id=device_hash[:32],
            device_code_hash=device_hash,
            user_code="BCDF-2345",
            name="MacBook",
            host_kind=RunnerHostKind.desktop,
            client_ip=None,
            status=PairingStatus.pending,
            created_at=NOW,
            expires_at=NOW + PAIRING_TTL,
        )

    async def purge(self, _before: datetime) -> int:
        return 0


def _service(clock: list[float]) -> RunnerPairingService:
    return RunnerPairingService(
        _Pairings(),  # type: ignore[arg-type]
        MagicMock(),
        MagicMock(),
        AsyncMock(),
        MagicMock(),
        clock=lambda: NOW,
        monotonic=lambda: clock[0],
    )


async def test__abandoned_pairings__forgotten_after_their_lifetime() -> None:
    clock = [1000.0]
    service = _service(clock)
    for _ in range(50):
        await service.poll(f"hsdc_{uuid4().hex}")
    assert len(service._last_poll) == 50

    clock[0] += PAIRING_TTL.total_seconds() + 1
    await service.purge()

    assert service._last_poll == {}


async def test__fresh_poll__evicts_stale_entries_without_waiting_for_purge() -> None:
    clock = [1000.0]
    service = _service(clock)
    await service.poll(f"hsdc_{uuid4().hex}")

    clock[0] += PAIRING_TTL.total_seconds() + 1
    await service.poll(f"hsdc_{uuid4().hex}")

    assert len(service._last_poll) == 1
