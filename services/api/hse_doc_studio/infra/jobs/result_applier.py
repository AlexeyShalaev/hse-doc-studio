"""Применение выходов удалённой задачи к тому проекта.

Выходы лежат в объектном хранилище под префиксом задачи. На том они попадают только по белому списку
вида задачи, через `safe_open` (ни один компонент пути не следует симлинку), с проверкой размера и sha256
и атомарной заменой файла. Повторное применение тех же выходов оставляет том как есть.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import uuid
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

import structlog

from hse_doc_studio.core.jobs.applier import (
    CODE_APPLY_FAILED,
    CODE_OUTPUT_MISMATCH,
    CODE_OUTPUT_MISSING,
    CODE_OUTPUT_NOT_ALLOWED,
    CODE_OUTPUT_UNSAFE_PATH,
    ApplyError,
)
from hse_doc_studio.core.jobs.artifacts import IArtifactStore, PublishPdfRequest
from hse_doc_studio.core.jobs.entities import JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import ArtifactRef, validate_relative_posix
from hse_doc_studio.core.jobs.office import OfficeConvertPayload
from hse_doc_studio.core.jobs.storage import IJobOutputIngest
from hse_doc_studio.core.projects.volume import IProjectVolume, UnsafePathError
from hse_doc_studio.core.storage.errors import ObjectNotFoundError, ObjectStoreError
from hse_doc_studio.core.storage.ingest import output_prefix
from hse_doc_studio.core.storage.ports import IObjectStore

logger = structlog.get_logger()

SUBMISSIONS_DIR = "submissions"
BUILD_DIR = ".build"


class VolumeJobResultApplier:
    def __init__(
        self,
        volume: IProjectVolume,
        store: IObjectStore,
        artifacts: IArtifactStore,
        ingest: IJobOutputIngest,
    ) -> None:
        self._volume = volume
        self._store = store
        self._artifacts = artifacts
        self._ingest = ingest

    async def apply(self, spec: JobSpec, artifacts: Sequence[ArtifactRef]) -> None:
        if not artifacts:
            return
        allowed = _allowed(spec)
        for ref in artifacts:
            self._check_path(ref, allowed)
        try:
            folder = self._volume.path_of(spec.project_id)
        except UnsafePathError as exc:
            raise ApplyError(CODE_OUTPUT_UNSAFE_PATH, str(exc)) from exc
        prefix = output_prefix(str(spec.project_id), str(spec.id))
        built = _built_target(spec)
        for ref in artifacts:
            await self._place(folder, prefix + ref.path, ref, built.get(ref.path, ref.path))
        if any(ref.path in built for ref in artifacts):
            await self._publish_pdf(spec, folder)

    async def discard(self, spec: JobSpec) -> None:
        try:
            await self._ingest.discard(spec.id)
        except Exception as exc:
            logger.warning("job outputs cleanup failed", job_id=str(spec.id), exc=repr(exc))

    @staticmethod
    def _check_path(ref: ArtifactRef, allowed: _Allowed) -> None:
        try:
            validate_relative_posix(ref.path)
        except ValueError as exc:
            raise ApplyError(CODE_OUTPUT_UNSAFE_PATH, str(exc)) from exc
        if not allowed.permits(ref.path):
            raise ApplyError(CODE_OUTPUT_NOT_ALLOWED, ref.path)

    async def _place(self, folder: Path, key: str, ref: ArtifactRef, target: str) -> None:
        try:
            if await asyncio.to_thread(self._already_there, folder, target, ref):
                return
            await self._write(folder, key, ref, target)
        except UnsafePathError as exc:
            raise ApplyError(CODE_OUTPUT_UNSAFE_PATH, f"{ref.path}: {exc}") from exc
        except ObjectNotFoundError as exc:
            raise ApplyError(CODE_OUTPUT_MISSING, ref.path) from exc
        except (OSError, ObjectStoreError) as exc:
            raise ApplyError(CODE_APPLY_FAILED, f"{ref.path}: {exc}") from exc

    def _already_there(self, folder: Path, target: str, ref: ArtifactRef) -> bool:
        try:
            handle = self._volume.safe_open(folder, target, "rb")
        except (FileNotFoundError, UnsafePathError):
            # Ссылка на месте файла не годится как «уже лежит»: её заменит атомарная запись, цель не тронется.
            return False
        digest = hashlib.sha256()
        size = 0
        with handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
        return size == ref.size and digest.hexdigest() == ref.sha256

    async def _write(self, folder: Path, key: str, ref: ArtifactRef, target: str) -> None:
        rel = PurePosixPath(target)
        tmp_rel = (rel.parent / f".tmp-{uuid.uuid4().hex[:12]}").as_posix()
        digest = hashlib.sha256()
        size = 0
        handle = await asyncio.to_thread(self._volume.safe_open, folder, tmp_rel, "wb", make_parents=True)
        try:
            with handle:
                async for chunk in self._store.stream(key):
                    digest.update(chunk)
                    size += len(chunk)
                    await asyncio.to_thread(handle.write, chunk)
            if size != ref.size or digest.hexdigest() != ref.sha256:
                raise ApplyError(CODE_OUTPUT_MISMATCH, ref.path)
            await asyncio.to_thread(os.replace, folder / tmp_rel, folder / target)
        except BaseException:
            with contextlib.suppress(OSError):
                (folder / tmp_rel).unlink(missing_ok=True)
            raise

    async def _publish_pdf(self, spec: JobSpec, folder: Path) -> None:
        payload = compile_payload_of(spec)
        await self._artifacts.publish_pdf(
            PublishPdfRequest(
                workspace=folder,
                doc_id=payload.doc_id,
                job_id=spec.id,
                source_file=payload.source_file,
                project_id=spec.project_id,
            )
        )


class _Allowed:
    """Что вид задачи вправе положить на том: точные пути и каталоги, внутри которых можно всё."""

    def __init__(self, exact: frozenset[str] = frozenset(), prefixes: tuple[str, ...] = ()) -> None:
        self._exact = exact
        self._prefixes = prefixes

    def permits(self, path: str) -> bool:
        return path in self._exact or any(path.startswith(prefix) for prefix in self._prefixes)


def _allowed(spec: JobSpec) -> _Allowed:
    match spec.kind:
        case JobKind.compile:
            return _Allowed(frozenset({_final_pdf(spec)}))
        case JobKind.office_convert:
            assert isinstance(spec.payload, OfficeConvertPayload)  # noqa: S101
            return _Allowed(frozenset({spec.payload.output_path}))
        case JobKind.pack_submission:
            return _Allowed(prefixes=(f"{SUBMISSIONS_DIR}/",))
    return _Allowed()


def _final_pdf(spec: JobSpec) -> str:
    source = PurePosixPath(compile_payload_of(spec).source_file)
    return (source.parent / f"{source.stem}.pdf").as_posix()


def _built_target(spec: JobSpec) -> dict[str, str]:
    """Куда класть выход вместо его пути: PDF сборки идёт в `.build/<doc_id>/`, откуда его переносит `publish_pdf`.

    Ключ объекта не может начинаться с точки, поэтому раннер называет PDF по итоговому пути, а место
    в `.build` определяет api.
    """
    if spec.kind is not JobKind.compile:
        return {}
    payload = compile_payload_of(spec)
    source = PurePosixPath(payload.source_file)
    built = (source.parent / BUILD_DIR / payload.doc_id / f"{source.stem}.pdf").as_posix()
    return {_final_pdf(spec): built}
