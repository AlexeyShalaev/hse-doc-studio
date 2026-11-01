from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.storage.ingest import OutputLimits, OutputRejectedError, OutputSpec
from hse_doc_studio.infra.storage.fs import FsObjectStore
from hse_doc_studio.infra.storage.job_output_ingest import ObjectJobOutputIngest

DATA = b"%PDF-1.7 output" * 50
SHA = hashlib.sha256(DATA).hexdigest()
SPEC = OutputSpec(path="out/a.pdf", size=len(DATA), sha256=SHA)
KEY = "artifacts/p1/jobs/j1/out/a.pdf"


@pytest.fixture
def objects(tmp_path: Path) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", max_object_bytes=1024 * 1024)


@pytest.fixture
def ingest(objects: FsObjectStore) -> ObjectJobOutputIngest:
    return ObjectJobOutputIngest(objects)


async def test__begin__disk_store__slots_have_own_prefix_and_no_url(ingest: ObjectJobOutputIngest) -> None:
    uploads = await ingest.begin("p1", "j1", [SPEC])

    assert [(u.path, u.key, u.url) for u in uploads] == [("out/a.pdf", KEY, None)]


async def test__commit__uploaded_output__returns_artifact_ref(
    ingest: ObjectJobOutputIngest, objects: FsObjectStore
) -> None:
    await objects.put(KEY, DATA)

    refs = await ingest.commit("p1", "j1", [SPEC])

    assert refs == [ArtifactRef(path="out/a.pdf", sha256=SHA, size=len(DATA))]


@pytest.mark.parametrize("job_id", ["../j2", "j1/../../x", "a/b", "", ".hidden"])
async def test__begin__foreign_job_id__rejected(ingest: ObjectJobOutputIngest, job_id: str) -> None:
    with pytest.raises(OutputRejectedError) as err:
        await ingest.begin("p1", job_id, [SPEC])

    assert err.value.code == "invalid_identifier"


@pytest.mark.parametrize("path", ["../j2/a.pdf", "/abs.pdf", "a/../../b", ".hidden/x", "a\\b"])
async def test__begin__path_escaping_prefix__rejected(ingest: ObjectJobOutputIngest, path: str) -> None:
    with pytest.raises(OutputRejectedError) as err:
        await ingest.begin("p1", "j1", [OutputSpec(path=path, size=1, sha256=SHA)])

    assert err.value.code == "invalid_output_path"


async def test__commit__object_of_other_job__not_visible(ingest: ObjectJobOutputIngest, objects: FsObjectStore) -> None:
    await objects.put("artifacts/p1/jobs/j2/out/a.pdf", DATA)

    with pytest.raises(OutputRejectedError) as err:
        await ingest.commit("p1", "j1", [SPEC])

    assert err.value.code == "output_missing"


async def test__commit__wrong_sha__rejected_and_object_removed(
    ingest: ObjectJobOutputIngest, objects: FsObjectStore
) -> None:
    await objects.put(KEY, b"x" * len(DATA))

    with pytest.raises(OutputRejectedError) as err:
        await ingest.commit("p1", "j1", [SPEC])

    assert err.value.code == "checksum_mismatch"
    assert await objects.head(KEY) is None


async def test__commit__wrong_size__rejected_and_object_removed(
    ingest: ObjectJobOutputIngest, objects: FsObjectStore
) -> None:
    await objects.put(KEY, DATA + b"tail")

    with pytest.raises(OutputRejectedError) as err:
        await ingest.commit("p1", "j1", [SPEC])

    assert err.value.code == "size_mismatch"
    assert await objects.head(KEY) is None


async def test__begin__oversize_and_overcount__rejected(ingest: ObjectJobOutputIngest) -> None:
    limits = OutputLimits(max_file_bytes=10, max_total_bytes=15, max_files=2)

    with pytest.raises(OutputRejectedError) as big:
        await ingest.begin("p1", "j1", [SPEC], limits=OutputLimits(max_file_bytes=10))
    with pytest.raises(OutputRejectedError) as total:
        await ingest.begin(
            "p1",
            "j1",
            [OutputSpec("a", 9, SHA), OutputSpec("b", 9, SHA)],
            limits=limits,
        )
    with pytest.raises(OutputRejectedError) as many:
        await ingest.begin("p1", "j1", [OutputSpec(f"f{i}", 1, SHA) for i in range(3)], limits=limits)

    assert (big.value.code, total.value.code, many.value.code) == (
        "output_too_large",
        "outputs_too_large",
        "too_many_outputs",
    )


async def test__begin__duplicate_and_bad_sha__rejected(ingest: ObjectJobOutputIngest) -> None:
    with pytest.raises(OutputRejectedError) as dup:
        await ingest.begin("p1", "j1", [SPEC, SPEC])
    with pytest.raises(OutputRejectedError) as bad:
        await ingest.begin("p1", "j1", [OutputSpec("a", 1, "XYZ")])

    assert (dup.value.code, bad.value.code) == ("duplicate_output", "invalid_sha256")


async def test__put__proxy_upload__verified_and_stored(ingest: ObjectJobOutputIngest, objects: FsObjectStore) -> None:
    ref = await ingest.put("p1", "j1", SPEC, DATA)

    assert ref.sha256 == SHA
    assert await objects.get(KEY) == DATA


async def test__put__wrong_sha__rejected_and_nothing_stored(
    ingest: ObjectJobOutputIngest, objects: FsObjectStore
) -> None:
    with pytest.raises(OutputRejectedError) as err:
        await ingest.put("p1", "j1", SPEC, b"y" * len(DATA))

    assert err.value.code == "checksum_mismatch"
    assert await objects.head(KEY) is None
