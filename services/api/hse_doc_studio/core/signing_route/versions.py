"""Новая версия на подписи: что изменилось у кандидата против версии, которую подписывают (раздел 12.6).

Кандидат это факты маршрута, где источник каждого документа заменён его текущей сборкой (`RouteFacts.candidate`).
Предпросмотр и отправка считают маршрут на кандидате; здесь чистые ответы на вопросы предпросмотра, события `sent`
и аудита: какие документы изменились, чьё согласие переносится целиком, кто потеряет согласие или подпись.

Документ сравнивается по sha256: кандидат (`compiled_sha256` кандидата) против снимка маршрута
(`DocSnapshot.compiled_sha256`, версия на подписи, снятая прошлой отправкой).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.signing_route.engine import RouteFacts, approval_token
from hse_doc_studio.core.signing_route.entities import Participant, SigningRoute


class DocChange(StrEnum):
    """Документ кандидата против версии на подписи (`SigningRoutePreview.docs[].change`, 12.9)."""

    same = "same"  # sha256 тот же: версия на подписи, B и подписи над ним остаются
    changed = "changed"  # sha256 другой: снимается новая версия на подписи, согласия по документу заново
    new = "new"  # маршрут документ ещё не отправлял (первая отправка, документ добавлен после отмены)


@dataclass(frozen=True)
class VersionChanges:
    """Изменения кандидата по документам маршрута, в порядке документов маршрута.

    `changed` и `kept` идут в событие `sent` (`details.changed`, `details.kept`) и аудит (`changed_docs`);
    `new` документы без прежней версии на подписи. Снимать версию на подписи нужно у `changed` и `new`
    (`to_pin`), у `kept` она остаётся как есть (`pinned_at`, B и подписи над ним).
    """

    docs: Mapping[str, DocChange]

    @property
    def changed(self) -> tuple[str, ...]:
        return tuple(doc_id for doc_id, change in self.docs.items() if change is DocChange.changed)

    @property
    def new(self) -> tuple[str, ...]:
        return tuple(doc_id for doc_id, change in self.docs.items() if change is DocChange.new)

    @property
    def kept(self) -> tuple[str, ...]:
        return tuple(doc_id for doc_id, change in self.docs.items() if change is DocChange.same)

    @property
    def to_pin(self) -> tuple[str, ...]:
        """Документы, у которых отправка снимает версию на подписи: изменившиеся и новые."""
        return tuple(doc_id for doc_id, change in self.docs.items() if change is not DocChange.same)

    @property
    def any(self) -> bool:
        """Есть что отправлять новой версией: иначе у `active` и `completed` отправка это `nothing_changed`."""
        return bool(self.to_pin)

    @property
    def new_version(self) -> bool:
        """Раунд меняет уже отправленный документ (`details.new_version` события `sent`, `new_version` запроса)."""
        return bool(self.changed)


def version_changes(route: SigningRoute, candidate: RouteFacts) -> VersionChanges:
    """Что изменилось у кандидата против версии на подписи по каждому документу маршрута."""
    return VersionChanges({doc_id: _change(route, candidate, doc_id) for doc_id in route.docs})


def _change(route: SigningRoute, candidate: RouteFacts, doc_id: str) -> DocChange:
    seen = route.snapshot.get(doc_id)
    if seen is None:
        return DocChange.new
    if seen.compiled_sha256 == candidate.doc(doc_id).compiled_sha256:
        return DocChange.same
    return DocChange.changed


def returning(route: SigningRoute, candidate: RouteFacts) -> tuple[UUID, ...]:
    """Пропущенные участники, которых отправка вернёт в маршрут: с их пропущенной пары снята отметку «необязательна»
    (раздел 13.3). Отправка с ними считается изменением: без изменений документов `nothing_changed` не отвечает."""
    return tuple(p.id for p in route.participants if p.skipped is not None and not still_optional(p, candidate))


def still_optional(p: Participant, candidate: RouteFacts) -> bool:
    """У пропущенного участника все пропущенные пары по-прежнему необязательны: пропуск переносится в новый раунд."""
    return p.skipped is not None and all(candidate.is_optional(pair) for pair in p.skipped.pairs)


def has_news(route: SigningRoute, candidate: RouteFacts) -> bool:
    """Есть что отправлять: документ изменился или в маршрут вернётся пропущенный участник."""
    return version_changes(route, candidate).any or bool(returning(route, candidate))


def keeps_approval(route: SigningRoute, candidate: RouteFacts, p: Participant) -> bool:
    """Согласие участника переносится по всем его документам (`SigningRoutePreview.participants[].keeps_approval`).

    Отпечатки его согласия совпадают с кандидатом у каждого его документа: после отправки он остаётся согласовавшим
    и шаги не держит. Раунд не важен: отправка переносит согласие в новый раунд всегда.
    """
    approval = p.approval
    if approval is None:
        return False
    return all(approval.tokens.get(doc_id) == approval_token(candidate.doc(doc_id)) for doc_id in p.doc_ids(route.docs))


def lost_docs(route: SigningRoute, candidate: RouteFacts, p: Participant) -> tuple[str, ...]:
    """Документы, по которым участник согласовал прежнюю версию, а кандидат другой: согласует их заново."""
    approval = p.approval
    if approval is None:
        return ()
    return tuple(
        doc_id
        for doc_id in p.doc_ids(route.docs)
        if doc_id in approval.tokens and approval.tokens[doc_id] != approval_token(candidate.doc(doc_id))
    )


def losing_approval(route: SigningRoute, candidate: RouteFacts) -> tuple[UUID, ...]:
    """Участники, которые согласовали (и, может быть, подписали) изменившийся документ: им новая версия
    (`signing_new_version` во «Входящие», если их очередь ещё не настала, 12.6). Отправитель первого шага сюда
    тоже попадает; исключить его, как и тех, кому сразу уходит запрос, решает сценарий."""
    return tuple(p.id for p in route.participants if lost_docs(route, candidate, p))
