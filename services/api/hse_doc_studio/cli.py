"""Командная строка Студии: `hse-doc-studio build` собирает документы проекта без запуска сервера.

Тот же конвейер, что и у кнопки «Собрать» (диспетчер задач, проверки, запись результата),
только без HTTP-приложения. Команду запускают файлы CI из Git-настроек проекта: образ Студии
с этой версией, проброшенный Docker и папка проекта, смонтированная по тому же пути.

Коды выхода: 0 — всё собрано, 1 — хотя бы один документ не собрался, 2 — неверные аргументы,
не проект или нет Docker.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

import structlog
from dishka import Provider, Scope, make_async_container, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.compile.errors import CompileSetupError
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import IProjectIndexRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.di.providers.repositories import LocalPersistenceProvider
from hse_doc_studio.infra.di.providers.services import DomainServiceProvider
from hse_doc_studio.infra.di.providers.use_cases import UseCaseProvider
from hse_doc_studio.infra.docker.cli import configure_docker_binary
from hse_doc_studio.use_cases.compile.build_project import BuildProjectInput, BuildProjectOutput, BuildProjectUC

_EXIT_OK = 0
_EXIT_BUILD_FAILED = 1
_EXIT_USAGE = 2
_PULL_FAILED = "__FAILED__"
_PULL_DONE = "__DONE__"


class _SingleProjectIndex:
    """Индекс из одной папки: CLI не трогает список проектов установки и не регистрирует в нём ничего."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list_known(self) -> list[Path]:
        return [self._folder]

    def register(self, folder: Path) -> None:
        return None

    def unregister(self, folder: Path) -> None:
        return None


class _CliProvider(Provider):
    scope = Scope.APP

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self._index = _SingleProjectIndex(folder)

    @provide(override=True)
    def get_project_index_repo(self) -> IProjectIndexRepository:
        return self._index


def _write(line: str, *, stream: TextIO | None = None) -> None:
    (stream or sys.stdout).write(line + "\n")


def _report(line: str) -> None:
    _write(line)


async def _build(folder: Path, out_dir: Path, doc_ids: tuple[str, ...] | None) -> BuildProjectOutput:
    configure_docker_binary(settings.docker_binary)
    container = make_async_container(
        LocalPersistenceProvider(), DomainServiceProvider(), UseCaseProvider(), _CliProvider(folder)
    )
    try:
        async with container() as scope:
            images = await scope.get(DockerImageManager)

            async def install_image(image: str) -> None:
                last = ""
                async for line in await images.pull(image):
                    if line == _PULL_FAILED:
                        raise CompileSetupError(f"docker pull failed: {image}\n{last}")
                    if line != _PULL_DONE:
                        last = line
                        _write(line)

            uc = await scope.get(BuildProjectUC)
            return await uc.execute(
                BuildProjectInput(
                    folder=folder, out_dir=out_dir, doc_ids=doc_ids, report=_report, install_image=install_image
                )
            )
    finally:
        await container.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hse-doc-studio", description="HSE Doc Studio")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="собрать документы проекта без сервера")
    build.add_argument("project_dir", nargs="?", default=".", type=Path, help="папка проекта (по умолчанию текущая)")
    scope = build.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", help="все документы проекта (по умолчанию)")
    scope.add_argument("--docs", nargs="+", metavar="ID", help="только эти документы")
    build.add_argument(
        "--out",
        type=Path,
        default=Path("build"),
        help="куда положить готовые файлы; относительный путь считается от папки проекта (по умолчанию build)",
    )
    db = sub.add_parser("db", help="миграции базы серверного режима")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="довести схему до последней ревизии")
    db_sub.add_parser("current", help="показать ревизию базы и head")
    db_sub.add_parser("check", help="проверить, что база на head и без дрейфа (код 1, если нет)")
    secrets_cmd = sub.add_parser("secrets", help="секреты серверного режима")
    secrets_sub = secrets_cmd.add_subparsers(dest="secrets_command", required=True)
    reencrypt = secrets_sub.add_parser(
        "reencrypt", help="перешифровать секреты в базе первичным ключом (после смены ключа, прежний в RETIRED_KEYS)"
    )
    reencrypt.add_argument("--dry-run", action="store_true", help="только посчитать, ничего не записывать")
    return parser


async def _reencrypt(*, dry_run: bool) -> int:
    from hse_doc_studio.core.secrets import encrypted_columns  # noqa: PLC0415
    from hse_doc_studio.infra.db.engine import create_engine  # noqa: PLC0415
    from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher  # noqa: PLC0415
    from hse_doc_studio.infra.secrets.reencrypt import reencrypt_all  # noqa: PLC0415
    from hse_doc_studio.infra.secrets.server_keys import SecretsKeyMissingError, server_key_store  # noqa: PLC0415

    try:
        cipher = FernetSecretCipher(server_key_store(settings))
    except SecretsKeyMissingError as exc:
        _write(f"error: {exc}", stream=sys.stderr)
        return _EXIT_USAGE
    engine = create_engine(settings.db)
    try:
        report = await reencrypt_all(engine, cipher, encrypted_columns, dry_run=dry_run)
    finally:
        await engine.dispose()
    verb = "будет перешифровано" if dry_run else "перешифровано"
    _write(f"{verb}: {report.updated}; уже на первичном ключе: {report.current}; нечитаемых: {len(report.unreadable)}")
    for item in report.unreadable:
        _write(f"unreadable: {item}", stream=sys.stderr)
    return _EXIT_OK if report.ok else _EXIT_BUILD_FAILED


async def _db(command: str) -> int:
    # extra server необязателен: local-режим не должен тянуть SQLAlchemy при импорте CLI
    from hse_doc_studio.infra.db import migrator  # noqa: PLC0415
    from hse_doc_studio.infra.db.engine import create_engine  # noqa: PLC0415

    engine = create_engine(settings.db)
    try:
        if command == "upgrade":
            await migrator.migrate_if_needed(engine)
            _write(f"ok: {await migrator.current_revision(engine)}")
            return _EXIT_OK
        current = await migrator.current_revision(engine)
        head = migrator.head_revision()
        _write(f"current: {current or '-'}\nhead: {head}")
        if command == "current":
            return _EXIT_OK
        if current != head:
            _write("db_outdated: выполните `hse-doc-studio db upgrade`", stream=sys.stderr)
            return _EXIT_BUILD_FAILED
        drift = await migrator.check_drift(engine)
        for diff in drift:
            _write(f"drift: {diff}", stream=sys.stderr)
        return _EXIT_BUILD_FAILED if drift else _EXIT_OK
    finally:
        await engine.dispose()


def _run_db(command: str) -> int:
    try:
        return asyncio.run(_db(command))
    except ImportError:
        _write("error: нужен extra server (uv sync --extra server)", stream=sys.stderr)
        return _EXIT_USAGE
    except RuntimeError as exc:
        _write(f"error: {exc}", stream=sys.stderr)
        return _EXIT_USAGE


def _run_secrets(*, dry_run: bool) -> int:
    try:
        return asyncio.run(_reencrypt(dry_run=dry_run))
    except ImportError:
        _write("error: нужен extra server (uv sync --extra server)", stream=sys.stderr)
        return _EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "db":
        return _run_db(args.db_command)
    if args.command == "secrets":
        return _run_secrets(dry_run=args.dry_run)
    folder = args.project_dir.expanduser().resolve()
    out_dir = args.out if args.out.is_absolute() else folder / args.out
    doc_ids = tuple(args.docs) if args.docs else None
    # Отчёт идёт в stdout, журнал Студии в stderr и только важное.
    previous = structlog.get_config()
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    try:
        result = asyncio.run(_build(folder, out_dir, doc_ids))
    except (ValueError, CompileSetupError, NotFoundError) as exc:
        _write(f"error: {exc}", stream=sys.stderr)
        return _EXIT_USAGE
    finally:
        structlog.configure(**previous)
    for failed in (doc for doc in result.documents if not doc.ok):
        _write(f"--- {failed.doc_id}: {failed.status.value} ---", stream=sys.stderr)
        _write(failed.log_tail, stream=sys.stderr)
    return _EXIT_OK if result.ok else _EXIT_BUILD_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
