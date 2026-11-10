"""Перенос маршрутов 0.20.0: версия на подписи из сборки, которую подписанты согласовали (signing-route.md, 12.11).

Маршрут 0.20.0 версии на подписи не снимал: снимок хранит только sha256 сборки на момент отправки
(`DocSnapshot.compiled_sha256`). Без версии на подписи источник подписи это текущая сборка, и первая же
пересборка с другим PDF остановила бы маршрут (`sent_changed`). Перенос ищет файл с тем же sha256 и делает его
версией на подписи:

1. текущая сборка документа, если её sha256 совпал со снимком;
2. иначе архив сборок документа (`IBuildArchive`): последние удачные сборки, байты сверяются по sha256;
3. иначе версию не восстановить: у документа остаётся `sent: null`, идущий маршрут останавливает сверка
   (`sent_changed`), у остановленного кнопка «Отправить новую версию».

Переносятся только документы маршрута в `HOLDING_STATUSES` без версии на подписи, отправленные до 0.21
(`DocSnapshot.sent_at` пуст: отправка R16 и новее его ставит и сама снимает версию). Подмену или удаление версии
на подписи мимо маршрута у маршрута новее перенос поэтому не прячет: её останавливает сверка (12.5).

Перенос идемпотентный: снятая версия есть в состоянии подписей, второй проход её не трогает, а несохранимое
(версии нет нигде) ничего не пишет. Аудит `signing_route.migrate` только у переноса, который что-то изменил:
снял версию или нашёл потерянную у маршрута, который из-за неё сейчас остановится.

Ни B, ни подписи над ним, ни согласия перенос не трогает: версия на подписи совпадает по байтам с тем, что
согласовали, поэтому согласия (`build:<sha>`) и B, зафиксированный из той же сборки, остаются действительными.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.enums import CompileStatus
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.repositories import ICompileRepository
from hse_doc_studio.core.signing_route.entities import HOLDING_STATUSES, WATCHING_STATUSES, SigningRoute
from hse_doc_studio.core.signing_route.ports import IBuildArchive
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signatures._doc_context import sha256_file
from hse_doc_studio.use_cases.signatures.signing_source import pinned_rel
from hse_doc_studio.use_cases.signing_route.pinning import RoutePinning
from hse_doc_studio.use_cases.signing_route.point import RoutePoint

logger = structlog.get_logger()

# Сколько последних удачных сборок документа держит архив (`infra.compile.pdf_archive.ARCHIVE_KEEP`).
ARCHIVE_DEPTH = 8


class BuildArchive:
    """`IBuildArchive` сервера: записи удачных сборок документа (новые первыми) и их PDF в хранилище артефактов.

    Сначала сборки с тем же отпечатком, затем без записанного отпечатка (старые записи); байты сверяются всегда.
    """

    def __init__(self, compiles: ICompileRepository, artifacts: IArtifactStore, *, depth: int = ARCHIVE_DEPTH) -> None:
        self._compiles = compiles
        self._artifacts = artifacts
        self._depth = depth

    async def find(self, project_id: UUID, folder: Path, doc_id: str, sha256: str) -> bytes | None:
        records = await self._compiles.list_for_document(folder, doc_id)
        recent = [r for r in reversed(records) if r.status is CompileStatus.success][: self._depth]
        ordered = [r for r in recent if r.output_sha256 == sha256] + [r for r in recent if r.output_sha256 is None]
        for record in ordered:
            try:
                content = await self._artifacts.read_archived_pdf(project_id, folder, doc_id, record.id)
            except (FileNotFoundError, OSError):
                continue
            if hashlib.sha256(content).hexdigest() == sha256:
                return content
        return None


class MigrationOutcome(StrEnum):
    pinned = "pinned"  # версия на подписи снята у всех документов маршрута, которым она была нужна
    needs_new_version = "needs_new_version"  # хотя бы у одного документа версию не восстановить


class RestoredFrom(StrEnum):
    build = "build"
    archive = "archive"


@dataclass(frozen=True)
class Migration:
    """Итог переноса маршрута: откуда снята версия каждого документа и чьей версии нет нигде."""

    restored: Mapping[str, RestoredFrom]
    sha256: Mapping[str, str]
    lost: tuple[str, ...]

    @property
    def outcome(self) -> MigrationOutcome:
        return MigrationOutcome.needs_new_version if self.lost else MigrationOutcome.pinned

    @property
    def docs(self) -> tuple[str, ...]:
        return (*self.restored, *self.lost)

    def audit_details(self) -> dict[str, object]:
        """Подробности `signing_route.migrate`: только идентификаторы и отпечатки, ни путей, ни содержимого."""
        return {
            "outcome": self.outcome.value,
            "docs": list(self.docs),
            "restored": [
                {"doc_id": doc_id, "sha256": self.sha256[doc_id], "from": source.value}
                for doc_id, source in self.restored.items()
            ],
            "lost": list(self.lost),
        }


def unmigrated_docs(route: SigningRoute, state: SignaturesState) -> tuple[str, ...]:
    """Документы маршрута 0.20.0 без версии на подписи, которые нужно перенести (в порядке маршрута)."""
    if route.status not in HOLDING_STATUSES:
        return ()
    found: list[str] = []
    for doc_id in route.docs:
        seen = route.snapshot.get(doc_id)
        if seen is None or seen.compiled_sha256 is None or seen.sent_at is not None:
            continue
        if doc_id not in state.pinned:
            found.append(doc_id)
    return tuple(found)


class RouteMigration:
    """Перенос одного маршрута; вызывать под блокировкой строки маршрута и `route_files` (`project_lock`)."""

    def __init__(self, pinning: RoutePinning, archive: IBuildArchive | None) -> None:
        self._pinning = pinning
        self._archive = archive

    async def migrate(self, point: RoutePoint, route: SigningRoute, *, at: datetime) -> Migration | None:
        """Снять версию на подписи у документов маршрута 0.20.0; None, если переносить нечего или нечего писать.

        `at` запасное время версии, если у маршрута нет `sent_at` (у отправленного оно есть всегда).
        """
        folder = point.project.folder
        docs = unmigrated_docs(route, self._pinning.state(folder))
        if not docs:
            return None
        restored: dict[str, RestoredFrom] = {}
        sources: dict[str, Path] = {}
        expected: dict[str, str] = {}
        lost: list[str] = []
        temps: list[Path] = []
        try:
            for doc_id in docs:
                sha256 = route.snapshot[doc_id].compiled_sha256
                assert sha256 is not None  # noqa: S101 — отобраны `unmigrated_docs`
                found = await self._locate(point, doc_id, sha256, temps)
                if found is None:
                    lost.append(doc_id)
                    continue
                source, path = found
                restored[doc_id] = source
                sources[doc_id] = path
                expected[doc_id] = sha256
            if expected:
                await self._pinning.pin(point, route, expected, at=route.sent_at or at, sources=sources)
        finally:
            for temp in temps:
                with contextlib.suppress(OSError):
                    temp.unlink(missing_ok=True)
        migration = Migration(restored=restored, sha256=expected, lost=tuple(lost))
        if not restored and route.status not in WATCHING_STATUSES:
            # Остановленный, возвращённый маршрут: версии нет нигде, и ничего не меняется; кнопка у него и так
            # «Отправить новую версию» (`changed` по снимку). Повторный проход тоже ничего не напишет.
            return None
        logger.info(
            "signing route migrated",
            route_id=str(route.id),
            outcome=migration.outcome.value,
            restored={doc_id: source.value for doc_id, source in restored.items()},
            lost=list(lost),
        )
        return migration

    async def _locate(
        self, point: RoutePoint, doc_id: str, sha256: str, temps: list[Path]
    ) -> tuple[RestoredFrom, Path] | None:
        working = self._pinning.working(point, doc_id)
        if working is not None and working.is_file() and await asyncio.to_thread(sha256_file, working) == sha256:
            return RestoredFrom.build, working
        if self._archive is None:
            return None
        folder = point.project.folder
        try:
            content = await self._archive.find(point.project_id, folder, doc_id, sha256)
        except Exception:  # noqa: BLE001 — хранилище недоступно: версия считается потерянной до следующего прохода
            logger.warning("build archive not read", doc_id=doc_id, exc_info=True)
            return None
        if content is None:
            return None
        target = folder / pinned_rel(doc_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.{uuid4().hex}.archive.tmp")
        temps.append(temp)
        await asyncio.to_thread(temp.write_bytes, content)
        return RestoredFrom.archive, temp
