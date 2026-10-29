"""LocalDiskArtifactStore: публикация PDF рядом с исходником и архив сборок."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.artifacts import PublishPdfRequest
from hse_doc_studio.infra.jobs import artifact_store
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore

_SOURCE = "vkr/vkr.tex"
PROJECT_ID = uuid4()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _request(workspace: Path) -> PublishPdfRequest:
    return PublishPdfRequest(workspace=workspace, doc_id="vkr", job_id=uuid4(), source_file=_SOURCE)


@pytest.mark.unit
@pytest.mark.asyncio
async def test__publish_pdf__moves_next_to_source__replaced_true(tmp_path: Path) -> None:
    _write(tmp_path / "vkr/.build/vkr/vkr.pdf", b"fresh")
    _write(tmp_path / "vkr/vkr.pdf", b"stale")

    outcome = await LocalDiskArtifactStore().publish_pdf(_request(tmp_path))

    assert outcome.replaced is True
    assert outcome.final_name == "vkr.pdf"
    assert (tmp_path / "vkr/vkr.pdf").read_bytes() == b"fresh"
    assert not (tmp_path / "vkr/.build/vkr/vkr.pdf").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test__publish_pdf__persistent_move_failure__five_retries_keeps_build_copy_replaced_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path / "vkr/.build/vkr/vkr.pdf", b"fresh")
    _write(tmp_path / "vkr/vkr.pdf", b"stale")
    attempts: list[str] = []

    def locked(src: str, dst: str) -> None:
        attempts.append(src)
        raise PermissionError("file is open in another program")

    monkeypatch.setattr(artifact_store.shutil, "move", locked)
    store = LocalDiskArtifactStore(move_attempts=5, retry_delay_s=0)

    outcome = await store.publish_pdf(_request(tmp_path))

    assert len(attempts) == 5
    assert outcome.replaced is False
    assert outcome.final_name == "vkr.pdf"
    assert (tmp_path / "vkr/.build/vkr/vkr.pdf").read_bytes() == b"fresh"
    assert (tmp_path / "vkr/vkr.pdf").read_bytes() == b"stale"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__publish_pdf__transient_failure__retries_then_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path / "vkr/.build/vkr/vkr.pdf", b"fresh")
    real_move = artifact_store.shutil.move
    calls = 0

    def flaky(src: str, dst: str) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError("locked")
        return str(real_move(src, dst))

    monkeypatch.setattr(artifact_store.shutil, "move", flaky)

    outcome = await LocalDiskArtifactStore(retry_delay_s=0).publish_pdf(_request(tmp_path))

    assert calls == 3
    assert outcome.replaced is True
    assert (tmp_path / "vkr/vkr.pdf").read_bytes() == b"fresh"


@pytest.mark.unit
async def test__archive_pdf__archives_build_copy_not_stale_neighbour_and_prunes_to_8(tmp_path: Path) -> None:
    store = LocalDiskArtifactStore()
    _write(tmp_path / "vkr/vkr.pdf", b"stale neighbour")
    _write(tmp_path / "vkr/.build/vkr/vkr.pdf", b"fresh build copy")
    first = uuid4()
    await store.archive_pdf(PROJECT_ID, tmp_path, "vkr", first, _SOURCE)
    assert await store.read_archived_pdf(PROJECT_ID, tmp_path, "vkr", first) == b"fresh build copy"

    ids = [first]
    (tmp_path / "vkr/.build/vkr/vkr.pdf").unlink()
    for i in range(10):
        _write(tmp_path / "vkr/vkr.pdf", f"build {i}".encode())
        job_id = uuid4()
        ids.append(job_id)
        await store.archive_pdf(PROJECT_ID, tmp_path, "vkr", job_id, _SOURCE)

    archive_dir = tmp_path / ".hse-studio" / "pdf-archive" / "vkr"
    assert len(list(archive_dir.glob("*.pdf"))) == 8
    assert await store.read_archived_pdf(PROJECT_ID, tmp_path, "vkr", ids[-1]) == b"build 9"
    with pytest.raises(FileNotFoundError):
        await store.read_archived_pdf(PROJECT_ID, tmp_path, "vkr", ids[0])


@pytest.mark.unit
async def test__read_archived_pdf__missing__file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await LocalDiskArtifactStore().read_archived_pdf(PROJECT_ID, tmp_path, "vkr", uuid4())
