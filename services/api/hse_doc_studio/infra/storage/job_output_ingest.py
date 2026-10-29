"""IJobOutputIngest поверх IObjectStore."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from hse_doc_studio.core.jobs.files import ArtifactRef, validate_relative_posix
from hse_doc_studio.core.storage.errors import ChecksumMismatchError, InvalidObjectKeyError, ObjectTooLargeError
from hse_doc_studio.core.storage.ingest import (
    OutputLimits,
    OutputRejectedError,
    OutputSpec,
    OutputUpload,
    output_prefix,
)
from hse_doc_studio.core.storage.keys import is_sha256, validate_key
from hse_doc_studio.core.storage.ports import IObjectStore, ObjectSource


class ObjectJobOutputIngest:
    def __init__(self, store: IObjectStore, *, limits: OutputLimits | None = None) -> None:
        self._store = store
        self._limits = limits or OutputLimits()

    async def begin(
        self,
        project_id: str,
        job_id: str,
        outputs: Sequence[OutputSpec],
        *,
        limits: OutputLimits | None = None,
        expires_in_s: int = 900,
    ) -> list[OutputUpload]:
        keys = self._plan(project_id, job_id, outputs, limits or self._limits)
        uploads: list[OutputUpload] = []
        for spec, key in zip(outputs, keys, strict=True):
            link = await self._store.presign_put(key, expires_in_s=expires_in_s)
            uploads.append(OutputUpload(path=spec.path, key=key, url=link))
        return uploads

    async def put(self, project_id: str, job_id: str, spec: OutputSpec, source: ObjectSource) -> ArtifactRef:
        (key,) = self._plan(project_id, job_id, [spec], self._limits)
        try:
            await self._store.put(key, source, sha256=spec.sha256)
        except ChecksumMismatchError as exc:
            raise OutputRejectedError("checksum_mismatch", "sha256 выхода не совпал с заявленным") from exc
        except ObjectTooLargeError as exc:
            raise OutputRejectedError("output_too_large", "выход больше предела") from exc
        await self._verify(key, spec)
        return ArtifactRef(path=spec.path, sha256=spec.sha256, size=spec.size)

    async def commit(
        self,
        project_id: str,
        job_id: str,
        outputs: Sequence[OutputSpec],
        *,
        limits: OutputLimits | None = None,
    ) -> list[ArtifactRef]:
        keys = self._plan(project_id, job_id, outputs, limits or self._limits)
        refs: list[ArtifactRef] = []
        for spec, key in zip(outputs, keys, strict=True):
            await self._verify(key, spec)
            refs.append(ArtifactRef(path=spec.path, sha256=spec.sha256, size=spec.size))
        return refs

    def _plan(self, project_id: str, job_id: str, outputs: Sequence[OutputSpec], limits: OutputLimits) -> list[str]:
        prefix = output_prefix(project_id, job_id)
        if len(outputs) > limits.max_files:
            raise OutputRejectedError("too_many_outputs", "слишком много выходов")
        if sum(spec.size for spec in outputs) > limits.max_total_bytes:
            raise OutputRejectedError("outputs_too_large", "выходы задачи больше предела")
        paths = [spec.path for spec in outputs]
        if len(set(paths)) != len(paths):
            raise OutputRejectedError("duplicate_output", "выход заявлен дважды")
        return [self._key_for(prefix, spec, limits) for spec in outputs]

    @staticmethod
    def _key_for(prefix: str, spec: OutputSpec, limits: OutputLimits) -> str:
        if spec.size < 0 or spec.size > limits.max_file_bytes:
            raise OutputRejectedError("output_too_large", f"выход больше предела: {spec.path}")
        if not is_sha256(spec.sha256):
            raise OutputRejectedError("invalid_sha256", f"некорректный sha256: {spec.path}")
        try:
            validate_relative_posix(spec.path)
            return validate_key(prefix + spec.path)
        except (ValueError, InvalidObjectKeyError) as exc:
            raise OutputRejectedError("invalid_output_path", f"путь выхода недопустим: {spec.path}") from exc

    async def _verify(self, key: str, spec: OutputSpec) -> None:
        info = await self._store.head(key)
        if info is None:
            raise OutputRejectedError("output_missing", f"выход не загружен: {spec.path}")
        if info.size != spec.size:
            await self._store.delete(key)
            raise OutputRejectedError("size_mismatch", f"размер выхода не совпал: {spec.path}")
        digest = hashlib.sha256()
        async for chunk in self._store.stream(key):
            digest.update(chunk)
        if digest.hexdigest() != spec.sha256:
            await self._store.delete(key)
            raise OutputRejectedError("checksum_mismatch", f"sha256 выхода не совпал: {spec.path}")
