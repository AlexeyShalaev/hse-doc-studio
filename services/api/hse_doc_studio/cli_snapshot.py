"""`db snapshot` и `db restore-snapshot`: снимок базы для апдейтера (docs/design/auto-update.md, раздел 5).

Снимок это обычный `pg_dump -Fc` одним файлом; восстановление идёт одной транзакцией («всё или ничего», схема
public пересоздаётся) и только при остановленных api и раннерах. Полные бэкапы с файлами и объектами остаются за
`hse-doc-studio backup`.
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

# Журнал запусков обновления живёт в той же базе, что откатывается: без этого восстановление стирает запись самого
# отката и успешного обновления перед ним (найдено на живом docker: апдейтер шлёт события в несуществующий запуск, а
# предыдущий запуск остаётся «running»). Строки update_runs переживают восстановление: временная таблица держит их
# на время транзакции, после дампа они возвращаются по общим столбцам (схема старой версии может быть другой).
_KEEP_RUNS = """\
DO $keep$ BEGIN
  IF to_regclass('public.update_runs') IS NOT NULL THEN
    CREATE TEMP TABLE _keep_update_runs AS SELECT * FROM public.update_runs;
  END IF;
END $keep$;
"""
_RETURN_RUNS = """\
DO $ret$
DECLARE cols text;
BEGIN
  IF to_regclass('pg_temp._keep_update_runs') IS NULL OR to_regclass('public.update_runs') IS NULL THEN
    RETURN;
  END IF;
  SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum)
    INTO cols
    FROM pg_attribute a
   WHERE a.attrelid = 'pg_temp._keep_update_runs'::regclass AND a.attnum > 0 AND NOT a.attisdropped
     AND EXISTS (SELECT 1 FROM pg_attribute b WHERE b.attrelid = 'public.update_runs'::regclass
                  AND b.attname = a.attname AND b.attnum > 0 AND NOT b.attisdropped);
  IF cols IS NULL THEN
    RETURN;
  END IF;
  -- Целиком: в снимке запуск мог быть «running», и индекс «один активный» не пустил бы второй.
  DELETE FROM public.update_runs;
  EXECUTE format('INSERT INTO public.update_runs (%s) SELECT %s FROM _keep_update_runs', cols, cols);
END $ret$;
"""


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
    # `pg_restore --clean` на живой базе падает на партиционированных таблицах («cannot drop inherited constraint»,
    # найдено на живом docker), поэтому схема public пересоздаётся скриптом, а дамп разворачивается в SQL и идёт
    # через psql: всё одной транзакцией, ошибка откатывает и DROP SCHEMA, база остаётся как была.
    restore_bin = await _binary("pg_restore")
    psql_bin = await _binary("psql")
    args, env = pg_env(_dsn())
    script = file.with_suffix(file.suffix + ".restore.sql")
    try:
        with script.open("w", encoding="utf-8") as out:
            out.write(_KEEP_RUNS + "DROP SCHEMA IF EXISTS public CASCADE;\nCREATE SCHEMA public;\n")
            out.flush()
            unpack = subprocess.run(  # noqa: S603
                [restore_bin, "--no-owner", "--no-acl", "--file", "-", str(file)],
                env=env,
                stdout=out,
                stderr=subprocess.PIPE,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
        if unpack.returncode != 0:
            return 1, f"pg_restore exited with {unpack.returncode}: {unpack.stderr.strip()[-800:]}"
        with script.open("a", encoding="utf-8") as out:
            out.write(_RETURN_RUNS)
        cmd = [psql_bin, "--single-transaction", "--quiet", "-v", "ON_ERROR_STOP=1", "--file", str(script), *args]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)  # noqa: S603
    finally:
        script.unlink(missing_ok=True)
    if proc.returncode != 0:
        return 1, f"psql exited with {proc.returncode}: {proc.stderr.strip()[-800:]}"
    return 0, f"ok: restored from {file}"
