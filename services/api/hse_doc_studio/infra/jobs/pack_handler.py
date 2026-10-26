"""Обработчик pack.submission: собирает папку и архив пакета сдачи по готовому плану."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path

import structlog

from hse_doc_studio.core.jobs.enums import JobErrorCategory
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.pack import PackResult, PackSkip, PackSubmissionPayload
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.infra.submission.pack_executor import (
    SUBMISSIONS_DIR,
    PackExecutor,
    SourceEscapesError,
    archive_ext,
    resolve_source,
)

logger = structlog.get_logger()

CODE_ARCHIVE_FAILED = "archive_failed"
CODE_MANIFEST_MISMATCH = "manifest_mismatch"
CODE_MANIFEST_FILE_MISSING = "manifest_file_missing"
CODE_INVALID_ENTRY = "invalid_entry"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _describe_folder(workspace: Path, rel_path: str) -> ArtifactRef:
    """Описание папки: хеш по путям и содержимому файлов в стабильном порядке, размер суммарный."""
    root = workspace / rel_path
    digest = hashlib.sha256()
    total = 0
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(file.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(file).encode("ascii"))
        total += file.stat().st_size
    return ArtifactRef(path=rel_path, sha256=digest.hexdigest(), size=total)


class PackHandler:
    """Обработчик pack.submission; регистрируется слайсом перехода CreateSubmissionUC."""

    def __init__(self, executor: PackExecutor | None = None) -> None:
        self._executor = executor or PackExecutor()

    async def handle(self, payload: PackSubmissionPayload, ctx: JobContext) -> PackResult:
        # Тело синхронное и тяжелое (штампы, архив), поэтому в потоке: цикл событий
        # остается свободным. Поток не прервать, так что отмену ждем до его конца.
        work = asyncio.ensure_future(asyncio.to_thread(self._build, payload, ctx))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            work.add_done_callback(lambda done: self._discard(done, payload, ctx.workspace))
            await asyncio.wait({work})
            raise

    def _build(self, payload: PackSubmissionPayload, ctx: JobContext) -> PackResult:
        workspace = ctx.workspace
        if payload.verify_manifest:
            self._verify_manifest(payload, workspace)
        try:
            executed = self._executor.execute(workspace, payload)
        except ValueError as exc:
            # Недопустимое имя записи (NUL, лишний символ) это ошибка входа, а не падение обработчика:
            # так же, как раньше, запрос получает 400, а не 500. Недоделанную папку убираем.
            shutil.rmtree(self._archive_base(payload, workspace), ignore_errors=True)
            raise JobFailure.of(JobErrorCategory.invalid_input, CODE_INVALID_ENTRY, str(exc)) from exc
        try:
            self._executor.create_archive(
                executed.folder, self._archive_base(payload, workspace), payload.archive_format.value
            )
        except ValueError as exc:
            raise JobFailure.of(JobErrorCategory.invalid_input, CODE_ARCHIVE_FAILED, str(exc)) from exc
        if not payload.keep_folder:
            shutil.rmtree(executed.folder, ignore_errors=True)
        return self._result(payload, ctx, executed.written, executed.skipped)

    @staticmethod
    def _archive_base(payload: PackSubmissionPayload, workspace: Path) -> Path:
        return workspace / SUBMISSIONS_DIR / payload.base_name

    @staticmethod
    def _verify_manifest(payload: PackSubmissionPayload, workspace: Path) -> None:
        for file in payload.manifest_files():
            if file.sha256 is None:
                continue
            try:
                path = resolve_source(workspace, file.path)
            except SourceEscapesError:
                raise JobFailure.of(JobErrorCategory.invalid_input, CODE_MANIFEST_FILE_MISSING, file.path) from None
            if not path.is_file():
                raise JobFailure.of(JobErrorCategory.invalid_input, CODE_MANIFEST_FILE_MISSING, file.path)
            if _file_sha256(path) != file.sha256:
                raise JobFailure.of(JobErrorCategory.invalid_input, CODE_MANIFEST_MISMATCH, file.path)

    @staticmethod
    def _result(
        payload: PackSubmissionPayload, ctx: JobContext, written: tuple[str, ...], skipped: tuple[PackSkip, ...]
    ) -> PackResult:
        folder_rel = f"{SUBMISSIONS_DIR}/{payload.base_name}"
        archive_rel = folder_rel + archive_ext(payload.archive_format)
        return PackResult(
            archive=ctx.outputs.describe(ctx.workspace, archive_rel),
            folder=_describe_folder(ctx.workspace, folder_rel) if payload.keep_folder else None,
            written=written,
            skipped=skipped,
        )

    def _discard(self, done: asyncio.Future[PackResult], payload: PackSubmissionPayload, workspace: Path) -> None:
        """Убирает папку и архив отмененной задачи; вызывается, когда поток уже закончил."""
        if not done.cancelled():
            done.exception()  # прочитать, чтобы цикл не жаловался на неполученную ошибку
        base = self._archive_base(payload, workspace)
        shutil.rmtree(base, ignore_errors=True)
        base.with_name(base.name + archive_ext(payload.archive_format)).unlink(missing_ok=True)
