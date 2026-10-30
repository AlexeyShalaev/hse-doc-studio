"""VolumeJobResultApplier: белый список путей, safe_open, проверка хеша и идемпотентность."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.applier import ApplyError
from hse_doc_studio.core.jobs.artifacts import PublishPdfOutcome, PublishPdfRequest
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.pack import PackSubmissionPayload
from hse_doc_studio.core.storage.ingest import output_prefix
from hse_doc_studio.infra.jobs.result_applier import VolumeJobResultApplier
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.storage.fs import FsObjectStore

from tests.unit.core.jobs.samples import make_compile_spec, make_office_spec, make_pack_spec

PROJECT = uuid4()


@dataclass
class FakeArtifacts:
    published: list[PublishPdfRequest] = field(default_factory=list)

    async def publish_pdf(self, req: PublishPdfRequest) -> PublishPdfOutcome:
        self.published.append(req)
        return PublishPdfOutcome(replaced=True, final_name="main.pdf")


class FakeIngest:
    def __init__(self) -> None:
        self.discarded: list[UUID] = []

    async def discard(self, job_id: UUID) -> None:
        self.discarded.append(job_id)


@dataclass
class Rig:
    applier: VolumeJobResultApplier
    store: FsObjectStore
    artifacts: FakeArtifacts
    ingest: FakeIngest
    folder: Path
    outside: Path

    def spec(self, base: JobSpec | None = None) -> JobSpec:
        return replace(base or make_compile_spec(), id=uuid4(), project_id=PROJECT, local_root=None)

    async def upload(self, spec: JobSpec, path: str, data: bytes) -> ArtifactRef:
        await self.store.put(output_prefix(str(spec.project_id), str(spec.id)) + path, data)
        return ArtifactRef(path=path, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    volume = LocalDiskProjectVolume(tmp_path / "volume")
    folder = volume.allocate(PROJECT)
    (folder / "tz").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    store = FsObjectStore(tmp_path / "objects", max_object_bytes=1 << 20)
    artifacts, ingest = FakeArtifacts(), FakeIngest()
    return Rig(VolumeJobResultApplier(volume, store, artifacts, ingest), store, artifacts, ingest, folder, outside)  # type: ignore[arg-type]


FINAL = "tz/main.pdf"
BUILT = "tz/.build/tz/main.pdf"


async def test__apply__compile_pdf__lands_in_build_dir_and_is_published(rig: Rig) -> None:
    spec = rig.spec()
    pdf = await rig.upload(spec, FINAL, b"%PDF-1")

    await rig.applier.apply(spec, [pdf])

    assert (rig.folder / BUILT).read_bytes() == b"%PDF-1"
    assert [(r.doc_id, r.source_file, r.project_id, r.job_id) for r in rig.artifacts.published] == [
        ("tz", "tz/main.tex", PROJECT, spec.id)
    ]
    assert [p.name for p in (rig.folder / "tz/.build/tz").iterdir() if p.name.startswith(".tmp")] == []


async def test__apply__same_outputs_twice__second_run_leaves_files_untouched(rig: Rig) -> None:
    spec = rig.spec()
    pdf = await rig.upload(spec, FINAL, b"%PDF-1")

    await rig.applier.apply(spec, [pdf])
    first = (rig.folder / BUILT).stat()
    await rig.applier.apply(spec, [pdf])

    second = (rig.folder / BUILT).stat()
    assert (first.st_ino, first.st_mtime_ns) == (second.st_ino, second.st_mtime_ns)
    assert (rig.folder / BUILT).read_bytes() == b"%PDF-1"


async def test__apply__build_dir_is_a_symlink__rejected_and_nothing_written_outside(rig: Rig) -> None:
    (rig.folder / "tz" / ".build").symlink_to(rig.outside, target_is_directory=True)
    spec = rig.spec()
    pdf = await rig.upload(spec, FINAL, b"%PDF-1")

    with pytest.raises(ApplyError) as raised:
        await rig.applier.apply(spec, [pdf])

    assert raised.value.code == "output_unsafe_path"
    assert list(rig.outside.rglob("*")) == []
    assert rig.artifacts.published == []


async def test__apply__target_file_is_a_symlink__link_replaced_and_target_untouched(rig: Rig) -> None:
    victim = rig.outside / "victim.pdf"
    victim.write_bytes(b"keep")
    (rig.folder / "tz" / ".build" / "tz").mkdir(parents=True)
    (rig.folder / BUILT).symlink_to(victim)
    spec = rig.spec()
    pdf = await rig.upload(spec, FINAL, b"%PDF-1")

    await rig.applier.apply(spec, [pdf])

    assert victim.read_bytes() == b"keep"
    assert not (rig.folder / BUILT).is_symlink()


@pytest.mark.parametrize("path", ["tz/main.tex", "other/main.pdf", ".hse-studio/x", "tz/.build/tz/main.pdf"])
async def test__apply__compile_path_outside_whitelist__rejected(rig: Rig, path: str) -> None:
    spec = rig.spec()

    with pytest.raises(ApplyError) as raised:
        await rig.applier.apply(spec, [ArtifactRef(path=path, sha256="a" * 64, size=1)])

    assert raised.value.code == "output_not_allowed"
    assert not (rig.folder / path).exists()


async def test__apply__content_differs_from_declared_hash__rejected_without_leftovers(rig: Rig) -> None:
    spec = rig.spec()
    good = await rig.upload(spec, FINAL, b"%PDF-1")
    forged = replace(good, sha256=hashlib.sha256(b"other").hexdigest())

    with pytest.raises(ApplyError) as raised:
        await rig.applier.apply(spec, [forged])

    assert raised.value.code == "output_mismatch"
    assert list((rig.folder / "tz/.build/tz").iterdir()) == []


async def test__apply__object_missing__output_missing(rig: Rig) -> None:
    spec = rig.spec()

    with pytest.raises(ApplyError) as raised:
        await rig.applier.apply(spec, [ArtifactRef(path=FINAL, sha256="a" * 64, size=1)])

    assert raised.value.code == "output_missing"


async def test__apply__office_convert__only_declared_output_path(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())
    good = await rig.upload(spec, "tz/_custom/ТЗ.pdf", b"%PDF")
    stray = await rig.upload(spec, "tz/_custom/other.pdf", b"%PDF")

    await rig.applier.apply(spec, [good])
    with pytest.raises(ApplyError) as raised:
        await rig.applier.apply(spec, [stray])

    assert (rig.folder / "tz/_custom/ТЗ.pdf").read_bytes() == b"%PDF"
    assert raised.value.code == "output_not_allowed"


async def test__apply__no_artifacts__nothing_happens(rig: Rig) -> None:
    await rig.applier.apply(rig.spec(), [])

    assert rig.artifacts.published == []


async def test__discard__delegates_to_ingest(rig: Rig) -> None:
    spec = rig.spec()

    await rig.applier.discard(spec)

    assert rig.ingest.discarded == [spec.id]


def _pack_spec(rig: Rig, *, keep_folder: bool) -> JobSpec:
    base = make_pack_spec()
    assert isinstance(base.payload, PackSubmissionPayload)
    return rig.spec(replace(base, payload=replace(base.payload, keep_folder=keep_folder)))


async def test__apply__pack__only_its_own_archive(rig: Rig) -> None:
    # Раннер хозяина с токеном задачи одного пакета не перезапишет чужие пакеты того же проекта.
    spec = _pack_spec(rig, keep_folder=False)
    own = await rig.upload(spec, "submissions/cp1-ivanov-20261026-093015-1a2b3c4d.zip", b"PK")
    other = await rig.upload(spec, "submissions/other.zip", b"PK")
    stray = await rig.upload(spec, "submissions/cp1-ivanov-20261026-093015-1a2b3c4d/a.pdf", b"%PDF")

    await rig.applier.apply(spec, [own])
    for forged in (other, stray):
        with pytest.raises(ApplyError) as raised:
            await rig.applier.apply(spec, [forged])
        assert raised.value.code == "output_not_allowed"

    assert (rig.folder / own.path).read_bytes() == b"PK"
    assert not (rig.folder / other.path).exists()


async def test__apply__pack_keep_folder__its_folder_allowed_and_siblings_not(rig: Rig) -> None:
    spec = _pack_spec(rig, keep_folder=True)
    inside = await rig.upload(spec, "submissions/cp1-ivanov-20261026-093015-1a2b3c4d/a.pdf", b"%PDF")
    sibling = await rig.upload(spec, "submissions/cp1-ivanov-20261026-093015-1a2b3c4d-x/a.pdf", b"%PDF")

    await rig.applier.apply(spec, [inside])
    with pytest.raises(ApplyError) as raised:
        await rig.applier.apply(spec, [sibling])

    assert raised.value.code == "output_not_allowed"
    assert (rig.folder / inside.path).read_bytes() == b"%PDF"
