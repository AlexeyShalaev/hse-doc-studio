"""Хранилище подключённых паков на диске: `data_dir/packs-store/` (docs/design/template-studio.md, 10.3 и 10.4).

```text
packs-store/catalog.json                        активный каталог: какие паки, шаблоны и версии сейчас в Студии
packs-store/<пак>/pack.yaml@<hex>               манифест пака по хешу содержимого
packs-store/<пак>/<шаблон>/template.yaml@<hex>  манифест шаблона по хешу содержимого
packs-store/<пак>/<шаблон>/<версия>@<hex>/      каталог версии по её дайджесту (как в releases.yaml)
```

Хранилище только дописывается: каталог версии кладётся копией через временную папку на том же томе, дайджест
сверяется до переименования, и существующий ключ не перезаписывается. `catalog.json` заменяется атомарно
(временный файл и `os.replace`); перечитывать его процессы решают по отпечатку файла (`stamp`).

Писатель один на хранилище: замок это файл `.lock`, созданный с `O_EXCL` (переносимо, без `fcntl`), с меткой
времени; брошенный упавшим процессом замок снимается по возрасту.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import structlog

from hse_doc_studio.core.catalog import PackOrigin, PackOriginKind
from hse_doc_studio.core.pack_catalog.store import (
    CATALOG_FORMAT,
    CatalogState,
    StoredPack,
    StoredTemplate,
    StoredVersion,
    is_store_name,
    version_store_path,
)
from hse_doc_studio.infra.template.releases import version_digest

logger = structlog.get_logger()

CATALOG_FILE = "catalog.json"
_LOCK_FILE = ".lock"
_STAGING_DIR = ".staging"
_STALE_LOCK_S = 900.0
_LOCK_WAIT_S = 30.0

Stamp = tuple[int, int, int]


class StoreLockTimeoutError(RuntimeError):
    """Замок хранилища держит другой процесс дольше, чем мы готовы ждать."""


class StoreIntegrityError(RuntimeError):
    """Копия каталога версии не совпала с дайджестом источника."""


def _origin_to_json(origin: PackOrigin) -> dict[str, Any]:
    data = asdict(origin)
    data["kind"] = origin.kind.value
    return data


def _origin_from_json(raw: Any) -> PackOrigin:
    if not isinstance(raw, dict):
        return PackOrigin(kind=PackOriginKind.subscribed)
    return PackOrigin(
        kind=PackOriginKind.subscribed,
        source_id=_str(raw.get("source_id")),
        source_kind=_str(raw.get("source_kind")),
        label=_str(raw.get("label")),
        url=_str(raw.get("url")),
        ref=_str(raw.get("ref")),
        revision=_str(raw.get("revision")),
        replaces_builtin=bool(raw.get("replaces_builtin", False)),
    )


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def state_to_json(state: CatalogState) -> dict[str, Any]:
    return {
        "format": CATALOG_FORMAT,
        "revision": state.revision,
        "updated_at": state.updated_at,
        "packs": [
            {
                "id": pack.id,
                "meta": pack.meta,
                "source_id": pack.source_id,
                "listed": pack.listed,
                "origin": _origin_to_json(pack.origin),
                "templates": [
                    {
                        "id": tpl.id,
                        "meta": tpl.meta,
                        "versions": [
                            {
                                "version": v.version,
                                "digest": v.digest,
                                "dir": v.dir,
                                "kind": v.kind,
                                "listed": v.listed,
                            }
                            for v in tpl.versions
                        ],
                    }
                    for tpl in pack.templates
                ],
            }
            for pack in state.packs
        ],
    }


def _rel_ok(value: Any) -> str | None:
    """Путь от корня хранилища без `..`, абсолютных частей и пустых сегментов; иначе None."""
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return value


def state_from_json(data: Any) -> CatalogState:
    """Терпимый разбор: битая запись пака или версии выпадает, остальное остаётся."""
    if not isinstance(data, dict) or int(data.get("format", 0) or 0) > CATALOG_FORMAT:
        return CatalogState()
    packs: list[StoredPack] = []
    for raw in data.get("packs") or []:
        pack = _pack_from_json(raw)
        if pack is not None:
            packs.append(pack)
    revision = data.get("revision")
    return CatalogState(
        revision=revision if isinstance(revision, int) else 0,
        updated_at=_str(data.get("updated_at")),
        packs=tuple(packs),
    )


def _pack_from_json(raw: Any) -> StoredPack | None:
    if not isinstance(raw, dict):
        return None
    pack_id, meta, source_id = raw.get("id"), _rel_ok(raw.get("meta")), raw.get("source_id")
    if not isinstance(pack_id, str) or not is_store_name(pack_id) or meta is None or not isinstance(source_id, str):
        return None
    templates: list[StoredTemplate] = []
    for tpl_raw in raw.get("templates") or []:
        if not isinstance(tpl_raw, dict):
            continue
        tpl_id, tpl_meta = tpl_raw.get("id"), _rel_ok(tpl_raw.get("meta"))
        if not isinstance(tpl_id, str) or not is_store_name(tpl_id) or tpl_meta is None:
            continue
        versions = tuple(v for v in (_version_from_json(item) for item in tpl_raw.get("versions") or []) if v)
        templates.append(StoredTemplate(id=tpl_id, meta=tpl_meta, versions=versions))
    origin = _origin_from_json(raw.get("origin"))
    return StoredPack(
        id=pack_id,
        meta=meta,
        source_id=source_id,
        origin=origin,
        templates=tuple(templates),
        listed=bool(raw.get("listed", True)),
    )


def _version_from_json(raw: Any) -> StoredVersion | None:
    if not isinstance(raw, dict):
        return None
    version, digest, directory = raw.get("version"), raw.get("digest"), _rel_ok(raw.get("dir"))
    if not isinstance(version, str) or not is_store_name(version) or not isinstance(digest, str) or directory is None:
        return None
    kind = raw.get("kind")
    return StoredVersion(
        version=version,
        digest=digest,
        dir=directory,
        kind=kind if isinstance(kind, str) else None,
        listed=bool(raw.get("listed", True)),
    )


@contextlib.contextmanager
def file_lock(lock: Path, *, wait_s: float = _LOCK_WAIT_S) -> Iterator[None]:
    """Замок между процессами: файл, созданный с `O_EXCL`; брошенный упавшим процессом снимается по возрасту."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if _lock_is_stale(lock):
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise StoreLockTimeoutError(str(lock)) from None
            time.sleep(0.05)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(f"{os.getpid()} {datetime.now(UTC).isoformat()}\n")
        break
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _lock_is_stale(lock: Path) -> bool:
    try:
        return time.time() - lock.stat().st_mtime > _STALE_LOCK_S
    except OSError:
        return False


class PacksStore:
    """Диск хранилища. Копии собираются в `.staging/` внутри него: переименование не пересекает тома."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @property
    def catalog_path(self) -> Path:
        return self._root / CATALOG_FILE

    # ── чтение ───────────────────────────────────────────────────────────────

    def stamp(self) -> Stamp | None:
        """Отпечаток `catalog.json` (время, размер, inode); None, если каталога ещё нет."""
        try:
            st = self.catalog_path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def read(self) -> CatalogState:
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return CatalogState()
        except (OSError, ValueError) as exc:
            logger.warning("packs store: catalog.json is unreadable", path=str(self.catalog_path), exc=str(exc))
            return CatalogState()
        return state_from_json(data)

    def resolve(self, rel: str) -> Path | None:
        """Путь внутри хранилища по записи каталога; None, если запись выходит за корень или это ссылка."""
        if _rel_ok(rel) is None:
            return None
        path = self._root / rel
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(self._root.resolve()):
                return None
        except OSError:
            return None
        return path

    def has_version(self, pack: str, template: str, version: str, digest: str) -> bool:
        return (self._root / version_store_path(pack, template, version, digest)).is_dir()

    # ── запись (под замком) ──────────────────────────────────────────────────

    def write(self, state: CatalogState) -> None:
        """Атомарная замена `catalog.json`."""
        self._root.mkdir(parents=True, exist_ok=True)
        body = json.dumps(state_to_json(state), ensure_ascii=False, indent=2)
        handle, name = tempfile.mkstemp(prefix="catalog.", suffix=".tmp", dir=self._root)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(body)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.catalog_path)
        finally:
            Path(name).unlink(missing_ok=True)

    def put_version(self, source: Path, pack: str, template: str, version: str, digest: str) -> str:
        """Каталог версии в хранилище по дайджесту; уже лежащий ключ не трогается. Возвращает путь от корня."""
        rel = version_store_path(pack, template, version, digest)
        target = self._root / rel
        if target.is_dir():
            return rel
        staging = self._staging()
        try:
            copy = staging / "version"
            shutil.copytree(source, copy, symlinks=True, ignore_dangling_symlinks=True)
            if any(p.is_symlink() for p in copy.rglob("*")):
                raise StoreIntegrityError(f"{pack}/{template}@{version}: в каталоге версии есть ссылки")
            actual = version_digest(copy)
            if actual != digest:
                raise StoreIntegrityError(f"{pack}/{template}@{version}: дайджест копии {actual}, ожидался {digest}")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.rename(copy, target)
            except OSError:
                # Кто-то положил тот же ключ раньше: содержимое по дайджесту то же самое.
                if not target.is_dir():
                    raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return rel

    def put_meta(self, pack: str, template: str | None, name: str, data: bytes) -> str:
        """Манифест пака (`template` None) или шаблона по хешу содержимого. Возвращает путь от корня."""
        if not is_store_name(pack) or (template is not None and not is_store_name(template)):
            raise ValueError(f"недопустимый ключ хранилища: {pack}/{template}")
        hex_part = hashlib.sha256(data).hexdigest()
        rel = f"{pack}/{name}@{hex_part}" if template is None else f"{pack}/{template}/{name}@{hex_part}"
        target = self._root / rel
        if target.is_file():
            return rel
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(prefix=".meta.", dir=target.parent)
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.replace(tmp_name, target)
        finally:
            Path(tmp_name).unlink(missing_ok=True)
        return rel

    @contextlib.contextmanager
    def locked(self, *, wait_s: float = _LOCK_WAIT_S) -> Iterator[None]:
        """Один писатель на хранилище среди всех процессов api."""
        self._root.mkdir(parents=True, exist_ok=True)
        with file_lock(self._root / _LOCK_FILE, wait_s=wait_s):
            yield

    def _staging(self) -> Path:
        base = self._root / _STAGING_DIR
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"put-{uuid.uuid4().hex}"
        path.mkdir()
        return path
