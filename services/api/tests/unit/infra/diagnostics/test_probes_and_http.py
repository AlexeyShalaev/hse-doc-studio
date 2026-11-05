"""Пробы самодиагностики на настоящих сокетах и каталоге, метрики и публичный эндпоинт."""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from hse_doc_studio.api.observability.diagnostics_metrics import diagnostics_collector
from hse_doc_studio.api.observability.install_diagnostics import build_public_router
from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus
from hse_doc_studio.core.diagnostics.state import CheckState
from hse_doc_studio.infra.diagnostics.probes import ObjectProbe, TlsProbe
from hse_doc_studio.infra.storage.fs import FsObjectStore
from httpx import ASGITransport, AsyncClient

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def _cert(tmp: Path, days: int) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    start = datetime.now(UTC) - timedelta(days=1)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(datetime.now(UTC) + timedelta(days=days, hours=1))
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp / "c.pem", tmp / "k.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


async def _serve(cert: Path, key: Path) -> tuple[asyncio.Server, int]:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)

    async def handle(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)
    return server, server.sockets[0].getsockname()[1]


async def test__tls_probe__reads_days_left_from_self_signed_certificate(tmp_path: Path) -> None:
    server, port = await _serve(*_cert(tmp_path, 40))
    try:
        facts = await TlsProbe().inspect(f"https://127.0.0.1:{port}")
    finally:
        server.close()
    assert facts.error is None
    assert facts.days_left in (40, 41)


async def test__tls_probe__unconfigured_http_and_unreachable() -> None:
    probe = TlsProbe()
    assert (await probe.inspect(None)).configured is False
    assert (await probe.inspect("http://example.org")).https is False
    closed = await probe.inspect("https://127.0.0.1:1")
    assert closed.configured
    assert closed.error is not None
    assert closed.days_left is None


async def test__object_probe__fs_roundtrip_leaves_no_probe_object(tmp_path: Path) -> None:
    store = FsObjectStore(tmp_path, max_object_bytes=1024 * 1024)

    facts = await ObjectProbe(store, bucket=None).roundtrip()  # type: ignore[arg-type]

    assert facts.error_stage is None
    assert facts.kind == "fs"
    assert await store.list_objects("diag-probe/") == []


class BrokenWrite:
    async def check(self) -> None: ...

    async def put(self, *a: object, **k: object) -> None:
        raise OSError("disk full")


class WrongRead(BrokenWrite):
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def put(self, *a: object, **k: object) -> None: ...

    async def get(self, key: str) -> bytes:
        return b"other"

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class BrokenCheck:
    async def check(self) -> None:
        raise OSError("no bucket")


async def test__object_probe__failure_stages() -> None:
    assert (await ObjectProbe(BrokenCheck(), bucket="b").roundtrip()).error_stage == "check"  # type: ignore[arg-type]
    assert (await ObjectProbe(BrokenWrite(), bucket="b").roundtrip()).error_stage == "write"  # type: ignore[arg-type]
    wrong = WrongRead()
    assert (await ObjectProbe(wrong, bucket="b").roundtrip()).error_stage == "mismatch"  # type: ignore[arg-type]
    assert len(wrong.deleted) == 1  # пробный объект убран и после расхождения


def _result(check: str, status: DiagStatus) -> CheckResult:
    return CheckResult(check, status, "r", {"secret": "x"}, NOW, 1500)


def test__metrics__expose_status_age_duration_and_overall() -> None:
    lines = list(
        diagnostics_collector(lambda: {"db": _result("db", DiagStatus.ok), "disk": _result("disk", DiagStatus.warn)})()
    )
    assert 'hse_diag_check_status{check="disk"} 1' in lines
    assert 'hse_diag_check_duration_seconds{check="db"} 1.500' in lines
    assert "hse_diag_overall_status 1" in lines
    assert not any("secret" in line for line in lines)
    assert list(diagnostics_collector(dict)()) == []


def test__metrics__accepted_warning_stays_visible_but_leaves_the_overall_status() -> None:
    results = {"db": _result("db", DiagStatus.ok), "backups": _result("backups", DiagStatus.warn)}

    lines = list(diagnostics_collector(lambda: results, lambda: {"backups"})())

    assert 'hse_diag_check_status{check="backups"} 1' in lines  # само значение не прячем: мониторинг видит факт
    assert 'hse_diag_check_accepted{check="backups"} 1' in lines
    assert 'hse_diag_check_accepted{check="db"} 0' in lines
    assert "hse_diag_overall_status 0" in lines
    failing = {**results, "disk": _result("disk", DiagStatus.fail)}
    assert "hse_diag_overall_status 2" in list(diagnostics_collector(lambda: failing, lambda: {"backups"})())


class _Service:
    def __init__(self, states: dict[str, CheckState], accepted: set[str] | None = None) -> None:
        self.states = states
        self.accepted = accepted or set()

    async def snapshot(self) -> dict[str, CheckState]:
        return self.states


class _Container:
    def __init__(self, service: _Service) -> None:
        self.service = service

    async def get(self, _type: object) -> _Service:
        return self.service


def _app(states: dict[str, CheckState], accepted: set[str] | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(build_public_router(_Container(_Service(states, accepted))))  # type: ignore[arg-type]
    return app


async def _get(states: dict[str, CheckState], accepted: set[str] | None = None) -> tuple[int, dict[str, object]]:
    async with AsyncClient(transport=ASGITransport(app=_app(states, accepted)), base_url="http://t") as client:
        res = await client.get("/health/diagnostics")
    return res.status_code, res.json()


async def test__public_endpoint__statuses_only_no_reasons_or_values() -> None:
    states = {
        "database": CheckState(_result("database", DiagStatus.ok), NOW),
        "disk": CheckState(_result("disk", DiagStatus.warn), NOW),
    }
    code, body = await _get(states)

    assert code == 200
    assert body["status"] == "warn"
    assert body["checks"] == {"database": "ok", "disk": "warn"}
    assert "secret" not in str(body)
    assert "reason" not in str(body)


async def test__public_endpoint__accepted_warning_is_marked_and_does_not_make_the_total_warn() -> None:
    states = {
        "database": CheckState(_result("database", DiagStatus.ok), NOW),
        "backups": CheckState(_result("backups", DiagStatus.warn), NOW),
    }
    code, body = await _get(states, {"backups"})

    assert (code, body["status"]) == (200, "ok")
    assert body["checks"] == {"backups": "accepted", "database": "ok"}


async def test__public_endpoint__fail_is_503_and_empty_is_unknown_503() -> None:
    code, body = await _get({"database": CheckState(_result("database", DiagStatus.fail), NOW)})
    assert (code, body["status"]) == (503, "fail")
    code, body = await _get({})
    assert (code, body["status"]) == (503, "unknown")
