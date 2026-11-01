"""`hse-doc-studio backup …`: список, запуск, проверка и восстановление бэкапов.

Восстановление выполняет оператор при остановленных api и раннерах.

Секреты в аргументы не передаются: ключи S3 берутся из BACKUP_S3_ACCESS_KEY и BACKUP_S3_SECRET_KEY, парольная фраза
из BACKUP_PASSPHRASE или файла `--passphrase-file`, ключ установки из HSE_STUDIO__SECRETS__KEY, как у api.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.backup.destinations import normalize_prefix, object_key
from hse_doc_studio.core.backup.entities import DestinationKind, DestinationSecrets, DestinationSpec, StoredBackup
from hse_doc_studio.core.backup.errors import BackupError
from hse_doc_studio.core.backup.protocols import TargetState
from hse_doc_studio.core.storage.ports import IObjectStore

_EXIT_OK = 0
_EXIT_FAILED = 1
_EXIT_USAGE = 2


def _write(line: str, *, stream: TextIO | None = None) -> None:
    (stream or sys.stdout).write(line + "\n")


def _err(line: str) -> None:
    _write(line, stream=sys.stderr)


def add_backup_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    backup = sub.add_parser("backup", help="бэкапы сервера: список, запуск, проверка, восстановление")
    actions = backup.add_subparsers(dest="backup_command", required=True)

    def source_args(p: argparse.ArgumentParser, *, backup_id: bool) -> None:
        group = p.add_argument_group("откуда брать бэкап")
        group.add_argument("--from-dir", type=Path, help="папка одного бэкапа (в ней manifest.json)")
        group.add_argument("--destination", help="назначение из базы этой установки (имя или id)")
        group.add_argument("--s3-bucket", help="бакет S3; ключи в BACKUP_S3_ACCESS_KEY и BACKUP_S3_SECRET_KEY")
        group.add_argument("--s3-endpoint", help="адрес S3 (пусто значит AWS)")
        group.add_argument("--s3-region", default="us-east-1")
        group.add_argument("--s3-prefix", default="", help="префикс бэкапов в бакете")
        group.add_argument("--s3-path-style", action="store_true", help="адресация bucket в пути (MinIO, Ceph)")
        if backup_id:
            group.add_argument("--backup-id", help="идентификатор бэкапа (для --s3-bucket и --destination)")
        p.add_argument("--passphrase-file", type=Path, help="файл с парольной фразой (или BACKUP_PASSPHRASE)")

    listing = actions.add_parser("list", help="показать бэкапы в назначении")
    source_args(listing, backup_id=False)
    run = actions.add_parser("run", help="снять бэкап сейчас в назначение (по умолчанию или --destination)")
    run.add_argument("--destination", help="имя или id назначения")
    verify = actions.add_parser("verify", help="проверить манифест и каждую часть, ничего не записывая")
    source_args(verify, backup_id=True)
    restore = actions.add_parser("restore", help="восстановить установку из бэкапа (без --apply только проверка)")
    source_args(restore, backup_id=True)
    restore.add_argument("--apply", action="store_true", help="выполнить восстановление")
    restore.add_argument("--overwrite", action="store_true", help="разрешить затереть непустую установку")


async def _store_from_args(args: argparse.Namespace) -> tuple[IObjectStore, str, str]:
    """Хранилище, префикс бэкапов и ключ папки одного бэкапа (пустой, если он указан папкой)."""
    from hse_doc_studio.infra.backup.stores import BackupStoreFactory  # noqa: PLC0415

    factory = BackupStoreFactory(settings.backups, settings.s3, settings.data_dir.expanduser())
    backup_id = getattr(args, "backup_id", None) or ""
    if getattr(args, "from_dir", None):
        from hse_doc_studio.infra.storage.fs import FsObjectStore  # noqa: PLC0415

        root = args.from_dir.expanduser().resolve()
        return FsObjectStore(root, max_object_bytes=settings.backups.max_object_bytes), "", ""
    if getattr(args, "s3_bucket", None):
        prefix = normalize_prefix(args.s3_prefix)
        spec = DestinationSpec(
            name="cli",
            kind=DestinationKind.s3,
            endpoint=args.s3_endpoint,
            region=args.s3_region,
            bucket=args.s3_bucket,
            prefix=prefix,
            path_style=args.s3_path_style,
        )
        secrets = DestinationSecrets(os.environ.get("BACKUP_S3_ACCESS_KEY"), os.environ.get("BACKUP_S3_SECRET_KEY"))
        if not (secrets.access_key and secrets.secret_key):
            msg = "задайте BACKUP_S3_ACCESS_KEY и BACKUP_S3_SECRET_KEY"
            raise _UsageError(msg)
        return factory.open(spec, secrets), prefix, object_key(prefix, backup_id) if backup_id else ""
    if getattr(args, "destination", None):
        service, stored = await _destination_service(args.destination)
        prefix = stored.destination.spec.prefix
        return service.open_store(stored), prefix, object_key(prefix, backup_id) if backup_id else ""
    msg = "укажите источник: --from-dir, --s3-bucket или --destination"
    raise _UsageError(msg)


class _UsageError(Exception):
    pass


async def _destination_service(name: str):  # type: ignore[no-untyped-def]
    from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository  # noqa: PLC0415
    from hse_doc_studio.core.mode import StudioMode  # noqa: PLC0415
    from hse_doc_studio.infra.di.containers.api import create_container  # noqa: PLC0415
    from hse_doc_studio.use_cases.backup.service import BackupService  # noqa: PLC0415

    container = create_container(StudioMode.server)
    repo = await container.get(IBackupDestinationRepository)
    stored = None
    for item in await repo.list_all():
        if name in {item.id, item.spec.name}:
            stored = await repo.get(item.id)
    if stored is None:
        msg = f"назначение {name!r} не найдено"
        raise _UsageError(msg)
    return await container.get(BackupService), stored


def _passphrase(args: argparse.Namespace) -> str | None:
    path = getattr(args, "passphrase_file", None)
    if path is not None:
        return path.expanduser().read_text(encoding="utf-8").strip()
    return os.environ.get("BACKUP_PASSPHRASE") or None


def _installation_keys() -> list[bytes]:
    from hse_doc_studio.infra.backup.runtime import raw_keys  # noqa: PLC0415
    from hse_doc_studio.infra.secrets.server_keys import SecretsKeyMissingError, server_key_store  # noqa: PLC0415

    try:
        return raw_keys(server_key_store(settings).load())
    except SecretsKeyMissingError:
        return []


def _fmt_size(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КиБ", "МиБ", "ГиБ", "ТиБ"):
        if value < 1024 or unit == "ТиБ":  # noqa: PLR2004
            return f"{value:.1f} {unit}" if unit != "Б" else f"{int(value)} Б"
        value /= 1024
    return f"{size} Б"


def _print_listing(items: Sequence[StoredBackup]) -> None:
    if not items:
        _write("бэкапов нет")
        return
    for item in items:
        m = item.manifest
        _write(
            f"{item.backup_id}  {m.created_at:%Y-%m-%d %H:%M:%S}Z  {_fmt_size(m.total_size):>10}  "
            f"версия {m.app_version}  схема {m.schema_revision or '-'}  шифрование {m.encryption_mode.value}"
        )


async def _list(args: argparse.Namespace) -> int:
    from hse_doc_studio.use_cases.backup.service import list_backups  # noqa: PLC0415

    store, prefix, _ = await _store_from_args(args)
    _print_listing(await list_backups(store, prefix))
    return _EXIT_OK


async def _run_now(args: argparse.Namespace) -> int:
    from hse_doc_studio.core.backup.entities import RunStatus, RunTrigger  # noqa: PLC0415

    if args.destination:
        service, stored = await _destination_service(args.destination)
        dest_id: str | None = stored.destination.id
    else:
        from hse_doc_studio.core.mode import StudioMode  # noqa: PLC0415
        from hse_doc_studio.infra.di.containers.api import create_container  # noqa: PLC0415
        from hse_doc_studio.use_cases.backup.service import BackupService  # noqa: PLC0415

        service = await create_container(StudioMode.server).get(BackupService)
        dest_id = None
    run = await service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
    if run.status is RunStatus.ok:
        _write(
            f"ok: {run.backup_id} в «{run.destination_name}», "
            f"{_fmt_size(run.size_bytes or 0)}, {run.duration_s or 0:.1f} с"
        )
        return _EXIT_OK
    _err(f"error: {run.status.value}: {run.error}")
    return _EXIT_FAILED


def _confirm(state: TargetState) -> bool:
    _write(
        f"ВНИМАНИЕ: будут затёрты данные установки: пользователей {state.users}, проектов {state.projects}, "
        f"объектов {state.objects}. Каталоги projects/, users/, gnupg/ будут переименованы в *.before-restore-*."
    )
    if not sys.stdin.isatty():
        _write("терминала нет: подтверждением служит флаг --overwrite")
        return True
    return input("введите overwrite для продолжения: ").strip() == "overwrite"


async def _restore(args: argparse.Namespace, *, verify_only: bool) -> int:
    from hse_doc_studio.infra.backup.parts import PartFetcher  # noqa: PLC0415
    from hse_doc_studio.infra.backup.pgtools import resolve_binary, server_major  # noqa: PLC0415
    from hse_doc_studio.infra.backup.restore_target import RestoreTarget  # noqa: PLC0415
    from hse_doc_studio.infra.backup.runtime import raw_keys  # noqa: F401, PLC0415
    from hse_doc_studio.infra.db.engine import async_dsn, create_engine  # noqa: PLC0415
    from hse_doc_studio.infra.storage.factory import create_object_store  # noqa: PLC0415
    from hse_doc_studio.use_cases.backup.restore import BackupSource, RestoreBackupUC  # noqa: PLC0415

    store, _prefix, base = await _store_from_args(args)
    if not base and not getattr(args, "from_dir", None):
        msg = "укажите --backup-id (список: hse-doc-studio backup list …)"
        raise _UsageError(msg)
    data_dir = settings.data_dir.expanduser()
    projects_root = (settings.server.projects_root or data_dir / "projects").expanduser()
    tmp_dir = (settings.backups.tmp_dir or data_dir / "tmp" / "backup").expanduser()
    engine = create_engine(settings.db)
    try:
        target = RestoreTarget(
            engine,
            async_dsn(settings.db.dsn),
            data_dir,
            projects_root,
            create_object_store(settings.s3, data_dir),
            pg_restore_binary=resolve_binary(settings.backups.pg_restore_binary, await server_major(engine)),
            timeout_s=settings.backups.dump_timeout_s,
        )
        uc = RestoreBackupUC(target, PartFetcher(tmp_dir))
        source = BackupSource(store, base)
        verified = await uc.load(source, installation_keys=_installation_keys(), passphrase=_passphrase(args))
        if verify_only:
            await uc.verify(source, verified, _write)
            _write(f"ok: бэкап {verified.manifest.backup_id} цел")
            return _EXIT_OK
        result = await uc.execute(
            source,
            verified,
            apply=args.apply,
            overwrite=args.overwrite,
            confirm=_confirm,
            report=_write,
        )
        if not result.applied:
            _write("для восстановления добавьте --apply")
        if result.applied:
            _clear_restore_marker()
            _write(
                f"готово: база {'восстановлена' if result.database else 'нет'}, файлов {result.files}, "
                f"объектов {result.objects}.\n"
                "Дальше: запустите api (миграции выполнятся сами), затем раннеры, проверьте /health/ready, "
                "войдите и соберите PDF."
            )
        return _EXIT_OK
    finally:
        await engine.dispose()


def _clear_restore_marker() -> None:
    """Прерванное восстановление из админки оставляет метку, из-за которой api стартует в режиме обслуживания."""
    from hse_doc_studio.infra.backup.maintenance import marker_path  # noqa: PLC0415

    marker_path(settings.data_dir.expanduser()).unlink(missing_ok=True)


def run_backup(args: argparse.Namespace) -> int:
    command = args.backup_command
    try:
        if command == "list":
            return asyncio.run(_list(args))
        if command == "run":
            return asyncio.run(_run_now(args))
        return asyncio.run(_restore(args, verify_only=command == "verify"))
    except _UsageError as exc:
        _err(f"error: {exc}")
        return _EXIT_USAGE
    except BackupError as exc:
        _err(f"error: {exc.message}")
        return _EXIT_FAILED
    except ImportError:
        _err("error: нужен extra server (uv sync --extra server)")
        return _EXIT_USAGE
