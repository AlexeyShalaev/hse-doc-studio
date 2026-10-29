"""Команда runner: контейнер без репозиториев ведёт verify, pack и office через настоящий цикл протокола.

Сервер подменён тестовым приложением с теми же строгими схемами тел, что и контракт раннера;
настоящая очередь серверной части в эту ветку ещё не влита.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
import zipfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from hse_doc_studio import cli
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.codec import encode_envelope
from hse_doc_studio.core.jobs.entities import JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.office import OfficeConvertPayload
from hse_doc_studio.core.jobs.pack import ArchiveFormat, PackEntry, PackEntryKind, PackSubmissionPayload
from hse_doc_studio.core.jobs.verify import TrustBundle, VerifyDetachedPayload
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.di.containers.runner import create_runner_container
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.loop import RunnerLoop

from tests.unit.infra.runner.fake_runner_api import TOKEN, FakeJob, FakeRunnerState, create_fake_app
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

PROJECT = uuid.UUID("22222222-2222-4222-8222-222222222222")
PDF = b"%PDF-1.7 signed body"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(state: FakeRunnerState, files: dict[str, bytes]) -> tuple[ManifestFile, ...]:
    for data in files.values():
        state.blobs[_sha(data)] = data
    return tuple(ManifestFile(path=p, sha256=_sha(d), size=len(d)) for p, d in files.items())


def _envelope(kind: JobKind, payload: Any, manifest: tuple[ManifestFile, ...]) -> dict[str, Any]:
    spec = JobSpec(
        id=uuid.uuid4(),
        kind=kind,
        tags=job_tags(kind, payload),
        project_id=PROJECT,
        actor=Actor.user("u1", "Иван"),
        locale=Lang.ru,
        payload=payload,
    )
    envelope = JobEnvelope(
        spec=spec, manifest=manifest, timeout_s=60.0, attempt=1, job_token="jt.secret", actor_role=Role.editor
    )
    return dict(encode_envelope(envelope))


class Rig:
    def __init__(
        self, tmp_path: Path, office_url: str | None, office_transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.state = FakeRunnerState()
        config = RunnerConfig(
            api_url="http://api",
            token=TOKEN,  # type: ignore[arg-type]
            name="test-runner",
            data_dir=tmp_path / "runner",
            office_url=office_url,
            poll_wait_s=0,
        )
        self.container = create_runner_container(
            config, transport=httpx.ASGITransport(app=create_fake_app(self.state)), office_transport=office_transport
        )
        self.task: asyncio.Task[None] | None = None
        self.loop: RunnerLoop | None = None

    async def start(self) -> None:
        self.loop = await self.container.get(RunnerLoop)
        self.task = asyncio.create_task(self.loop.run())

    async def finish(self, job: FakeJob) -> dict[str, Any]:
        async with asyncio.timeout(20):
            while not job.completed:
                await asyncio.sleep(0.02)
        return job.completed[0]

    async def stop(self) -> None:
        if self.loop is not None:
            self.loop.request_stop()
        if self.task is not None:
            await self.task
        await self.container.close()


@pytest_asyncio.fixture
async def rig(tmp_path: Path) -> AsyncIterator[Rig]:
    r = Rig(tmp_path, office_url=None)
    await r.start()
    yield r
    await r.stop()


async def test_runner_registers_with_detected_tags(rig: Rig) -> None:
    async with asyncio.timeout(10):
        while not rig.state.registrations:
            await asyncio.sleep(0.02)

    registration = rig.state.registrations[0]
    assert registration["name"] == "test-runner"
    assert {"verify", "pack"} <= set(registration["tags"])
    assert "office" not in registration["tags"]


async def test_verify_job_runs_with_ephemeral_keyring_and_reports_verdict(rig: Rig) -> None:
    ident = make_identity()
    pdf = ManifestFile("docs/final.pdf", _sha(PDF), len(PDF))
    payload = VerifyDetachedPayload(
        pdf=pdf,
        signature=InlineBlob.from_bytes(make_detached_cms(ident, PDF)),
        trust=TrustBundle(roots=(InlineBlob.from_bytes(ident.cert_der),)),
    )
    job = rig.state.enqueue(_envelope(JobKind.verify_detached, payload, _manifest(rig.state, {"docs/final.pdf": PDF})))

    done = await rig.finish(job)

    assert done["result"]["status"] == "succeeded"
    signature = done["result"]["data"]["signature"]
    assert signature["verdict"] == "valid"
    assert signature["chain"] == "trusted"
    assert done["artifacts"] == []
    assert job.log_lines[0].startswith("signature.verify_detached")
    # Блоб манифеста скачан с токеном этой задачи.
    assert rig.state.blob_requests == [(job.job_id, "jt.secret")]


async def test_verify_job_with_garbage_signature_fails_with_typed_error(rig: Rig) -> None:
    payload = VerifyDetachedPayload(
        pdf=ManifestFile("final.pdf", _sha(PDF), len(PDF)),
        signature=InlineBlob.from_bytes(b"not a signature"),
        trust=TrustBundle(),
    )
    job = rig.state.enqueue(_envelope(JobKind.verify_detached, payload, _manifest(rig.state, {"final.pdf": PDF})))

    done = await rig.finish(job)

    assert done["result"]["status"] == "failed"
    assert done["result"]["error"]["code"] == "unknown_signature_format"


async def test_pack_job_uploads_the_archive_and_leaves_no_folder_artifact(rig: Rig) -> None:
    source = b"report body"
    payload = PackSubmissionPayload(
        base_name="cp1-ivanov",
        profile_id="cp1",
        lang=Lang.ru,
        archive_format=ArchiveFormat.zip,
        keep_folder=False,
        verify_manifest=True,
        entries=(
            PackEntry(
                kind=PackEntryKind.copy,
                arcname="Отчёт.txt",
                source=ManifestFile("report.txt", _sha(source), len(source)),
            ),
            PackEntry(kind=PackEntryKind.text, arcname="README.txt", text="привет"),
        ),
    )
    job = rig.state.enqueue(_envelope(JobKind.pack_submission, payload, _manifest(rig.state, {"report.txt": source})))

    done = await rig.finish(job)

    assert done["result"]["status"] == "succeeded"
    (artifact,) = done["artifacts"]
    assert artifact["path"] == "submissions/cp1-ivanov.zip"
    archive = job.artifacts[artifact["sha256"]]
    assert _sha(archive) == artifact["sha256"]
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        assert sorted(zf.namelist()) == ["README.txt", "Отчёт.txt"]
        assert zf.read("Отчёт.txt") == source


async def test_pack_job_with_tampered_blob_fails_without_running(rig: Rig) -> None:
    source = b"report body"
    manifest = _manifest(rig.state, {"report.txt": source})
    rig.state.blobs[_sha(source)] = b"substituted"
    payload = PackSubmissionPayload(
        base_name="cp1",
        profile_id="cp1",
        lang=Lang.ru,
        archive_format=ArchiveFormat.zip,
        keep_folder=False,
        entries=(PackEntry(kind=PackEntryKind.text, arcname="a.txt", text="x"),),
    )
    job = rig.state.enqueue(_envelope(JobKind.pack_submission, payload, manifest))

    done = await rig.finish(job)

    assert done["result"]["status"] == "failed"
    assert done["result"]["error"]["code"] == "blob_unavailable"
    assert done["artifacts"] == []


async def test_office_job_without_converter_is_not_advertised_and_fails_typed(rig: Rig) -> None:
    payload = OfficeConvertPayload(source=ManifestFile("deck.pptx", _sha(b"x"), 1), output_path="deck.pdf")
    job = rig.state.enqueue(_envelope(JobKind.office_convert, payload, _manifest(rig.state, {"deck.pptx": b"x"})))

    done = await rig.finish(job)

    assert done["result"]["status"] == "failed"
    assert done["result"]["error"]["code"] == "unsupported_kind"


async def test_office_job_converts_through_gotenberg(tmp_path: Path) -> None:
    gotenberg = httpx.MockTransport(lambda request: httpx.Response(200, content=b"%PDF-converted"))
    rig = Rig(tmp_path, office_url="http://gotenberg:3000", office_transport=gotenberg)
    await rig.start()
    try:
        deck = b"pptx bytes"
        payload = OfficeConvertPayload(source=ManifestFile("deck.pptx", _sha(deck), len(deck)), output_path="deck.pdf")
        job = rig.state.enqueue(_envelope(JobKind.office_convert, payload, _manifest(rig.state, {"deck.pptx": deck})))

        done = await rig.finish(job)
    finally:
        await rig.stop()

    assert rig.state.registrations[0]["tags"].count("office") == 1
    assert done["result"]["status"] == "succeeded"
    assert done["result"]["data"]["status"] == "ok"
    (artifact,) = done["artifacts"]
    assert artifact["path"] == "deck.pdf"
    assert job.artifacts[artifact["sha256"]] == b"%PDF-converted"


def test_runner_command_without_settings_is_a_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("API_URL", "TOKEN"):
        monkeypatch.delenv(f"HSE_RUNNER__{name}", raising=False)

    assert cli.main(["runner"]) == 2


async def test_restart_reuses_saved_identity_and_does_not_register_again(tmp_path: Path) -> None:
    first = Rig(tmp_path, office_url=None)
    await first.start()
    await _until(lambda: first.state.registrations)
    await first.stop()
    assert (tmp_path / "runner" / "identity.json").stat().st_mode & 0o777 == 0o600

    second = Rig(tmp_path, office_url=None)
    await second.start()
    await _until(lambda: second.state.polls >= 1)
    await second.stop()

    assert second.state.registrations == []


async def _until(predicate: Callable[[], object], timeout_s: float = 10.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not predicate():
            await asyncio.sleep(0.02)
