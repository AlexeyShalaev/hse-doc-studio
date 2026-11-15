"""Хранилище предпросмотра на диске (порт IPreviewStore, docs/design/template-studio.md, 6.3).

`data_dir/pack-studio/previews/`:

- `work/<id сборки>/` синтетический проект сборки (на сервере это том предпросмотра: имя папки это id задачи);
  убирается после сборки, результат переезжает в кэш;
- `builds/<id>.json` и `builds/<id>.log` запись сборки и её журнал;
- `cache/<ключ>/` готовая сборка по ключу: `document.pdf`, `anchors.json` (якоря мест подписей), `build.log`,
  `meta.json`;
- `tmp/` копии пака для рендера в песочнице.

Записи и кэш ограничены по числу и возрасту (`prune`): это предпросмотр, его всегда можно собрать заново.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.pack_studio.preview import PreviewBuild, PreviewCheck, PreviewError, PreviewStatus
from hse_doc_studio.core.pack_studio.protocols import CachedPreview
from hse_doc_studio.core.signatures.anchors import ANCHORS_SUFFIX
from hse_doc_studio.infra.compile.pdf_archive import built_pdf_path, final_pdf_path

logger = structlog.get_logger()

WORK_DIR = "work"
BUILDS_DIR = "builds"
CACHE_DIR = "cache"
TMP_DIR = "tmp"
_PDF = "document.pdf"
_ANCHORS = "anchors.json"
_LOG = "build.log"
_META = "meta.json"
_CHECKS = "checks.json"
# Журнал сборки предпросмотра больше этого не хранится: хвост важнее начала.
MAX_LOG_BYTES = 512 * 1024


class FsPreviewStore:
    def __init__(self, root: Path, *, max_cache_entries: int, max_age_s: float) -> None:
        self._root = root
        self._max_cache = max_cache_entries
        self._max_age_s = max_age_s

    @property
    def work_root(self) -> Path:
        return self._root / WORK_DIR

    @property
    def tmp_root(self) -> Path:
        return self._root / TMP_DIR

    # ── папки сборок ────────────────────────────────────────────────────────

    def work_dir(self, build_id: UUID) -> Path:
        folder = self.work_root / str(build_id)
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        return folder

    def discard_work(self, build_id: UUID) -> None:
        shutil.rmtree(self.work_root / str(build_id), ignore_errors=True)

    # ── записи сборок ───────────────────────────────────────────────────────

    def save(self, build: PreviewBuild) -> None:
        _atomic_write(self._build_file(build.id, ".json"), json.dumps(_to_json(build), ensure_ascii=False))

    def load(self, build_id: UUID) -> PreviewBuild | None:
        try:
            raw = json.loads(self._build_file(build_id, ".json").read_text(encoding="utf-8"))
            return _from_json(raw)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save_log(self, build_id: UUID, log: str) -> None:
        _atomic_write(self._build_file(build_id, ".log"), _tail(log))

    def read_log(self, build: PreviewBuild) -> str | None:
        for path in (self._build_file(build.id, ".log"), self._cache_dir(build.key) / _LOG):
            with contextlib.suppress(OSError):
                return path.read_text(encoding="utf-8")
        return None

    # ── кэш ─────────────────────────────────────────────────────────────────

    def cached(self, key: str) -> CachedPreview | None:
        folder = self._cache_dir(key)
        try:
            meta = json.loads((folder / _META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not (folder / _PDF).is_file():
            return None
        with contextlib.suppress(OSError):
            os.utime(folder)  # свежесть для вытеснения: давно не нужные записи уходят первыми
        return CachedPreview(
            key=key,
            pages=meta.get("pages"),
            source_file=str(meta.get("source_file") or ""),
            has_anchors=(folder / _ANCHORS).is_file(),
            checks=_read_checks(folder / _CHECKS),
        )

    def keep(  # noqa: PLR0913 — что положить в кэш
        self,
        key: str,
        build_id: UUID,
        source_file: str,
        doc_id: str,
        log: str,
        pages: int | None,
        checks: tuple[PreviewCheck, ...] | None = None,
    ) -> CachedPreview | None:
        work = self.work_root / str(build_id)
        built = built_pdf_path(work, doc_id, source_file)
        pdf = built if built.is_file() else final_pdf_path(work, source_file)
        if not pdf.is_file() or pdf.is_symlink():
            return None
        folder = self._cache_dir(key)
        staging = folder.with_name(f"{folder.name}.{build_id.hex[:8]}.tmp")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        shutil.copyfile(pdf, staging / _PDF)
        anchors = _anchors_file(work, doc_id, source_file)
        if anchors.is_file() and not anchors.is_symlink():
            shutil.copyfile(anchors, staging / _ANCHORS)
        (staging / _LOG).write_text(_tail(log), encoding="utf-8")
        meta = {"pages": pages, "source_file": source_file, "build_id": str(build_id), "kept_at": time.time()}
        (staging / _META).write_text(json.dumps(meta), encoding="utf-8")
        if checks is not None:
            (staging / _CHECKS).write_text(json.dumps(_checks_json(checks), ensure_ascii=False), encoding="utf-8")
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(staging, folder)
        return CachedPreview(
            key=key,
            pages=pages,
            source_file=source_file,
            has_anchors=(folder / _ANCHORS).is_file(),
            checks=checks,
        )

    def pdf(self, key: str) -> Path | None:
        path = self._cache_dir(key) / _PDF
        return path if path.is_file() else None

    def anchors(self, key: str) -> bytes | None:
        with contextlib.suppress(OSError):
            return (self._cache_dir(key) / _ANCHORS).read_bytes()
        return None

    # ── уборка ──────────────────────────────────────────────────────────────

    def prune(self) -> None:
        now = time.time()
        self._prune_dir(self._root / BUILDS_DIR, now, files=True)
        self._prune_dir(self.work_root, now, files=False)
        self._prune_dir(self.tmp_root, now, files=False)
        self._prune_cache()

    def _prune_dir(self, folder: Path, now: float, *, files: bool) -> None:
        if not folder.is_dir():
            return
        for entry in folder.iterdir():
            try:
                old = now - entry.lstat().st_mtime > self._max_age_s
            except OSError:
                continue
            if not old:
                continue
            if files and entry.is_file():
                with contextlib.suppress(OSError):
                    entry.unlink()
            elif not files and entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)

    def _prune_cache(self) -> None:
        folder = self._root / CACHE_DIR
        if not folder.is_dir():
            return
        entries = []
        for entry in folder.iterdir():
            with contextlib.suppress(OSError):
                entries.append((entry.stat().st_mtime, entry))
        entries.sort(key=lambda item: item[0], reverse=True)
        for _mtime, entry in entries[self._max_cache :]:
            shutil.rmtree(entry, ignore_errors=True)

    # ── пути ────────────────────────────────────────────────────────────────

    def _build_file(self, build_id: UUID, suffix: str) -> Path:
        return self._root / BUILDS_DIR / f"{build_id}{suffix}"

    def _cache_dir(self, key: str) -> Path:
        if not key or any(ch not in "0123456789abcdef" for ch in key):
            raise ValueError(f"not a cache key: {key!r}")
        return self._root / CACHE_DIR / key


def _anchors_file(work: Path, doc_id: str, source_file: str) -> Path:
    stem = PurePosixPath(source_file).stem
    return built_pdf_path(work, doc_id, source_file).parent / f"{stem}{ANCHORS_SUFFIX}"


def _tail(text: str) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= MAX_LOG_BYTES:
        return text
    return raw[-MAX_LOG_BYTES:].decode("utf-8", errors="ignore")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def _to_json(build: PreviewBuild) -> dict[str, Any]:
    return {
        "id": str(build.id),
        "owner_id": build.owner_id,
        "workspace_id": str(build.workspace_id),
        "pack": build.pack,
        "template": build.template,
        "version": build.version,
        "document": build.document,
        "example": build.example,
        "combination": dict(build.combination),
        "key": build.key,
        "status": build.status.value,
        "cached": build.cached,
        "created_at": build.created_at.isoformat(),
        "started_at": _iso(build.started_at),
        "finished_at": _iso(build.finished_at),
        "pages": build.pages,
        "error": None if build.error is None else {"code": build.error.code, "detail": build.error.detail},
        "source_file": build.source_file,
        "has_anchors": build.has_anchors,
        "with_checks": build.with_checks,
        "checks": None if build.checks is None else _checks_json(build.checks),
    }


def _checks_json(checks: tuple[PreviewCheck, ...]) -> list[dict[str, Any]]:
    return [
        {"rule_id": c.rule_id, "severity": c.severity, "message": c.message, "file": c.file, "line": c.line}
        for c in checks
    ]


def _checks_of(raw: Any) -> tuple[PreviewCheck, ...] | None:
    if not isinstance(raw, list):
        return None
    return tuple(
        PreviewCheck(
            rule_id=str(item["rule_id"]),
            severity=str(item["severity"]),
            message=str(item.get("message") or ""),
            file=item.get("file"),
            line=item.get("line"),
        )
        for item in raw
        if isinstance(item, dict) and "rule_id" in item and "severity" in item
    )


def _read_checks(path: Path) -> tuple[PreviewCheck, ...] | None:
    try:
        return _checks_of(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def _from_json(raw: dict[str, Any]) -> PreviewBuild:
    error = raw.get("error")
    created = _dt(raw["created_at"])
    if created is None:
        raise ValueError("created_at")
    return PreviewBuild(
        id=UUID(raw["id"]),
        owner_id=raw.get("owner_id"),
        workspace_id=UUID(raw["workspace_id"]),
        pack=str(raw["pack"]),
        template=str(raw["template"]),
        version=str(raw["version"]),
        document=str(raw["document"]),
        example=str(raw["example"]),
        combination={str(k): str(v) for k, v in dict(raw.get("combination") or {}).items()},
        key=str(raw["key"]),
        status=PreviewStatus(raw["status"]),
        cached=bool(raw.get("cached")),
        created_at=created,
        started_at=_dt(raw.get("started_at")),
        finished_at=_dt(raw.get("finished_at")),
        pages=raw.get("pages"),
        error=None if not error else PreviewError(code=str(error["code"]), detail=error.get("detail")),
        source_file=raw.get("source_file"),
        has_anchors=bool(raw.get("has_anchors")),
        with_checks=bool(raw.get("with_checks")),
        checks=_checks_of(raw.get("checks")),
    )
