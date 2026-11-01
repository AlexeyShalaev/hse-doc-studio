"""`db snapshot` и `db restore-snapshot`: снимок базы для апдейтера (docs/design/auto-update.md, раздел 5).

Снимок это обычный `pg_dump -Fc` одним файлом; восстановление идёт одной транзакцией («всё или ничего») и только
при остановленных api и раннерах. Полные бэкапы с файлами и объектами остаются за `hse-doc-studio backup`.
"""

from __future__ import annotations

import hashlib
import subprocess  # noqa: S404 — тонкая обёртка над pg_dump и pg_restore
from pathlib import Path

from hse_doc_studio.api.config import settings
from hse_doc_studio.infra.backup.pgtools import resolve_binary, server_major
from hse_doc_studio.infra.backup.producers import pg_env
from hse_doc_studio.infra.db.engine import create_engine

_TIMEOUT_S = 6 * 3600.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


async def _binary(name: str) -> str:
    engine = create_engine(settings.db)
    try:
        return resolve_binary(name, await server_major(engine))
    finally:
        await engine.dispose()


def _dsn() -> str:
    dsn = settings.db.dsn
    if not dsn:
        msg = "HSE_STUDIO__DB__DSN is not set"
        raise RuntimeError(msg)
    return dsn


async def snapshot(out: Path) -> tuple[int, str]:
    """Снимает базу в `out`; пишет рядом `<out>.sha256`. Возвращает код выхода и строку для вывода."""
    binary = await _binary("pg_dump")
    args, env = pg_env(_dsn())
    tmp = out.with_suffix(out.suffix + ".part")
    cmd = [binary, "--format=custom", "--no-owner", "--no-acl", "--file", str(tmp), *args]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)  # noqa: S603
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        return 1, f"pg_dump exited with {proc.returncode}: {proc.stderr.strip()[-800:]}"
    tmp.replace(out)
    digest = _sha256(out)
    out.with_suffix(out.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
    return 0, f"ok: {out} {out.stat().st_size} bytes sha256={digest}"


async def restore(file: Path) -> tuple[int, str]:
    """Восстанавливает базу из снимка одной транзакцией, сверив контрольную сумму, если она лежит рядом."""
    if not file.is_file():
        return 2, f"snapshot not found: {file}"
    sum_file = file.with_suffix(file.suffix + ".sha256")
    if sum_file.is_file() and sum_file.read_text(encoding="utf-8").strip() != _sha256(file):
        return 1, "snapshot checksum mismatch: the file is damaged"
    binary = await _binary("pg_restore")
    args, env = pg_env(_dsn())
    cmd = [
        binary,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        "--single-transaction",
        "--exit-on-error",
        *args,
        str(file),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)  # noqa: S603
    if proc.returncode != 0:
        return 1, f"pg_restore exited with {proc.returncode}: {proc.stderr.strip()[-800:]}"
    return 0, f"ok: restored from {file}"
