"""Версия на подписи маршрута: снятие при отправке и новой версии, снятие при отмене (signing-route.md, 12.3, 12.4).

Пишут её только сценарии маршрута под `project_lock` (`route_files`), поэтому сверка маршрутов свои же записи не
видит. Снятие: копия собранного PDF во временный файл рядом с `pinned_rel(doc)`, sha256 копии, сверка с тем, что
видел автор (кандидат предпросмотра, `expected`), затем переименование и запись `SignaturesState.pinned`. Хэш
считается по копии: сборка, закончившаяся в эту секунду, не подменит байты после сверки. Не совпало: 409
`doc_changed`, ничего не записано.

Если транзакция маршрута упадёт после записи файлов, снимок в Postgres останется прежним, и следующая сверка
остановит маршрут (`sent_changed`): состояние безопасное, автор отправит ещё раз.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signing_route.entities import SigningRoute
from hse_doc_studio.core.signing_route.readiness import DocChangedError
from hse_doc_studio.core.value_objects import PinnedPdf
from hse_doc_studio.use_cases.signatures._doc_context import sha256_file
from hse_doc_studio.use_cases.signatures.signing_source import pinned_file, pinned_rel
from hse_doc_studio.use_cases.signing_route.point import RoutePoint


@dataclass(frozen=True)
class PinnedVersion:
    """Снятая версия на подписи: что ушло подписантам (событие `sent` и аудит, 12.6)."""

    doc_id: str
    sha256: str
    size: int


@dataclass(frozen=True)
class _Staged:
    doc_id: str
    temp: Path
    target: Path
    sha256: str
    size: int


class RoutePinning:
    """Версии на подписи документов маршрута в папке проекта. Вызывать под `project_lock` сценария."""

    def __init__(self, signatures: ISignatureRepository, template_service: ProjectTemplateService) -> None:
        self._signatures = signatures
        self._template_service = template_service

    async def pin(
        self, point: RoutePoint, route: SigningRoute, expected: Mapping[str, str], *, at: datetime
    ) -> tuple[PinnedVersion, ...]:
        """Снять версию на подписи у документов `expected` (документ: sha256 кандидата) для раунда `route.round`.

        Источник копии это текущая сборка; у документа без сборки прежняя версия на подписи (кандидат её и
        оставил, 12.6). Сначала копии всех документов и сверка, потом переименования и одна запись состояния.
        """
        if not expected:
            return ()
        folder = point.project.folder
        state = self._signatures.get_state(folder)
        staged: list[_Staged] = []
        try:
            for doc_id, sha256 in expected.items():
                staged.append(await self._stage(point, state.pinned.get(doc_id), doc_id, sha256))
            for item in staged:
                await asyncio.to_thread(os.replace, item.temp, item.target)
        finally:
            for item in staged:
                with contextlib.suppress(OSError):
                    item.temp.unlink(missing_ok=True)
        moment = at.astimezone(UTC).isoformat()
        pinned = dict(state.pinned)
        for item in staged:
            pinned[item.doc_id] = PinnedPdf(
                path=pinned_rel(item.doc_id),
                sha256=item.sha256,
                size=item.size,
                pinned_at=moment,
                route_id=str(route.id),
                round=route.round,
            )
        self._signatures.save_state(folder, replace(state, pinned=pinned))
        return tuple(PinnedVersion(item.doc_id, item.sha256, item.size) for item in staged)

    async def _stage(self, point: RoutePoint, previous: PinnedPdf | None, doc_id: str, sha256: str) -> _Staged:
        folder = point.project.folder
        source = self._working(point, doc_id)
        if (source is None or not source.is_file()) and previous is not None:
            source = pinned_file(folder, previous)
        if source is None or not source.is_file():
            raise DocChangedError([doc_id])
        target = folder / pinned_rel(doc_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(shutil.copyfile, source, temp)
            copied = await asyncio.to_thread(sha256_file, temp)
        except OSError:
            with contextlib.suppress(OSError):
                temp.unlink(missing_ok=True)
            raise DocChangedError([doc_id]) from None
        if copied != sha256:
            # Сборка изменилась после предпросмотра: автор отправляет не то, что видел.
            with contextlib.suppress(OSError):
                temp.unlink(missing_ok=True)
            raise DocChangedError([doc_id])
        return _Staged(doc_id, temp, target, copied, temp.stat().st_size)

    def _working(self, point: RoutePoint, doc_id: str) -> Path | None:
        """Путь текущей сборки документа; None, если документа нет или сборки у него не бывает."""
        doc = point.documents.get(doc_id)
        if doc is None:
            return None
        try:
            _, output_file = self._template_service.resolve_instance_source(point.project, doc, point.version)
        except (NotFoundError, ValueError):
            return None
        return point.project.folder / output_file if output_file else None

    def unpin(self, point: RoutePoint, route: SigningRoute) -> tuple[str, ...]:
        """Снять версии на подписи, которые снял этот маршрут (отмена, 12.4); документы в порядке маршрута.

        Сначала запись состояния, затем удаление файлов: не удалось удалить, лишний файл в `frozen` ничего не
        значит. B и подписи над ним остаются в состоянии подписей (5.6).
        """
        folder = point.project.folder
        state = self._signatures.get_state(folder)
        mine = {doc_id: pinned for doc_id, pinned in state.pinned.items() if pinned.route_id == str(route.id)}
        if not mine:
            return ()
        self._signatures.save_state(
            folder, replace(state, pinned={k: v for k, v in state.pinned.items() if k not in mine})
        )
        for pinned in mine.values():
            path = pinned_file(folder, pinned)
            if path is not None:
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)
        order = [doc_id for doc_id in route.docs if doc_id in mine]
        return (*order, *sorted(doc_id for doc_id in mine if doc_id not in route.docs))
