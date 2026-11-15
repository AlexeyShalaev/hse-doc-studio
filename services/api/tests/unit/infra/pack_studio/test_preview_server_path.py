"""Серверный путь сборки предпросмотра: вход задачи с тома предпросмотра без кэша хешей, выходы раннера туда же.

Папка сборки `previews/work/<id задачи>` устроена как папка проекта на томе (имя это id), поэтому загрузчик входа и
применение выходов те же, что у сборок проектов; отличаются реестр (строк кэша хешей нет: они ссылаются на проекты)
и публикация PDF (не в архив проекта).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.storage.ingest import output_prefix
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from hse_doc_studio.infra.jobs.result_applier import VolumeJobResultApplier
from hse_doc_studio.infra.pack_studio.preview_dispatch import NoHashCacheRegistry
from hse_doc_studio.infra.pack_studio.preview_store import FsPreviewStore
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.storage.blob_uploader import ManifestBlobUploader
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.fs import FsObjectStore

from tests.fakes.blob_registry import InMemoryBlobRegistry
from tests.unit.core.jobs.samples import make_compile_spec


class FakeIngest:
    def __init__(self) -> None:
        self.discarded: list[UUID] = []

    async def discard(self, job_id: UUID) -> None:
        self.discarded.append(job_id)


async def test__preview_volume__input_upload_skips_hash_cache_and_outputs_land_in_the_build_folder(
    tmp_path: Path,
) -> None:
    store = FsPreviewStore(tmp_path / "previews", max_cache_entries=10, max_age_s=3600)
    build_id = uuid4()
    work = store.work_dir(build_id)
    (work / "tz").mkdir()
    (work / "tz" / "main.tex").write_text("\\documentclass{article}", encoding="utf-8")
    volume = LocalDiskProjectVolume(store.work_root)
    objects = FsObjectStore(tmp_path / "objects", max_object_bytes=1 << 20)
    registry = InMemoryBlobRegistry()
    # Файлы «давно не менялись»: обычный загрузчик записал бы строки кэша хешей со ссылкой на проект.
    uploader = ManifestBlobUploader(
        volume, NoHashCacheRegistry(registry), ObjectBlobStore(objects), clock_ns=lambda: time.time_ns() + 10**10
    )

    manifest = await uploader.ensure(build_id, volume.path_of(build_id), ["tz/main.tex"])

    assert [f.path for f in manifest] == ["tz/main.tex"]
    assert registry.cache == {}
    assert set(registry.blobs) == {manifest[0].sha256}

    spec = replace(make_compile_spec(), id=build_id, project_id=build_id, local_root=work)
    pdf = b"%PDF-1.4 preview"
    await objects.put(output_prefix(str(build_id), str(build_id)) + "tz/main.pdf", pdf)
    ref = ArtifactRef(path="tz/main.pdf", sha256=hashlib.sha256(pdf).hexdigest(), size=len(pdf))
    applier = VolumeJobResultApplier(volume, objects, LocalDiskArtifactStore(), FakeIngest())  # type: ignore[arg-type]

    await applier.apply(spec, [ref])
    kept = store.keep("ab" * 32, build_id, "tz/main.tex", "tz", "log", 1)

    assert (work / "tz" / "main.pdf").read_bytes() == pdf
    assert kept is not None
    assert store.pdf("ab" * 32) is not None
    assert store.pdf("ab" * 32).read_bytes() == pdf  # type: ignore[union-attr]
