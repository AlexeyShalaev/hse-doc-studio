"""Сравнения результатов для эндпоинтов: `compare`, `impact`, `matrix` (template-studio-outcome.md, 4.5, 4.6, O7).

Всё только читает: ничего не пишет, не собирает и не отправляет (R15). Версию читает служба результата
(`PackOutcomeService.prepare`): права, три состояния (`work_tree`, `head`, `base`, последние два из git без checkout,
`diff_base_unavailable` с причинами `no_git`, `no_base`, `new_version`), `revision`, день и набор данных; ключ ответа и
ETag строятся от её ключей, поэтому `If-None-Match` отвечает 304 без расчёта, а правка манифеста, сценария или базы
меняет ключ.

- **`compare`**: два результата (две стороны: состояние, сценарий, набор данных, вводные), изменения со знаками и
  причинами, сводка по разделам. Два расчёта идут в пуле службы результата под её пределом (5 с).
- **`impact`**: «изменится N из M сценариев»: каждый сценарий шаблона (из рабочего дерева) на базе и в рабочем дереве, а
  с `include_atlas` ещё и строки таблицы атласа. Атлас берётся у `PackAtlasService` (его кэш, семафор и срок); строки
  «до» считаются прямым расчётом той же комбинации на базе.
- **`matrix`**: строка на сценарий, клетка на раздел, статус клетки; `against: base` подсвечивает отличия от базы.
- **Пределы.** `impact` и `matrix` идут в потоке под семафором (два одновременных на процесс), срок 20 с проверяется
  между расчётами сценариев (поток останавливается сам); по истечении и при полной очереди `outcome_busy` (503 с
  `Retry-After`). Сценариев не больше 200 (предел шаблона). Ответ больше предела размера это `outcome_too_large` (413,
  `limit`, `size`). Одинаковые одновременные запросы делят один расчёт; ответы кэшируются по ключу.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.scenarios import Scenario
from hse_doc_studio.core.pack_studio.outcome.serving import LruCache, etag_matches, etag_of, request_key
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.use_cases.pack_studio.outcome.compare import (
    Side,
    SideInputError,
    VersionSide,
    atlas_impact,
    compare_body,
    compare_sides,
    impact_body,
    matrix_body,
    matrix_rows,
    scenario_impacts,
)
from hse_doc_studio.use_cases.pack_studio.outcome_atlas import PackAtlasService
from hse_doc_studio.use_cases.pack_studio.outcome_service import (
    OutcomeReply,
    OutcomeState,
    PackOutcomeService,
    PreparedVersion,
)
from hse_doc_studio.use_cases.pack_studio.preview import examples_of
from hse_doc_studio.use_cases.pack_studio.scenario_service import (
    parse_scenario_files,
    scenario_digests,
    select_scenario_files,
)

BaseName = Literal["base", "head"]

# Предел размера ответа (JSON, байты): `impact` по 200 сценариям с причинами укладывается, пятьдесят мегабайт нет.
RESPONSE_LIMIT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class CompareLimits:
    # Срок расчёта `impact` и `matrix` и число одновременных на процесс; предел размера ответа; размеры кэшей.
    timeout_s: float = 20.0
    concurrency: int = 2
    response_bytes: int = RESPONSE_LIMIT_BYTES
    compare_entries: int = 128
    heavy_entries: int = 32
    cache_bytes: int = 64 * 1024 * 1024
    retry_after_s: int = 5


@dataclass(frozen=True)
class Subject:
    """Одна сторона сравнения (`OutcomeSubject` контракта)."""

    state: OutcomeState = "work_tree"
    scenario: str | None = None
    example: str | None = None
    inputs: Mapping[str, str] = field(default_factory=dict)


class _Deadline(Exception):  # noqa: N818 — расчёт остановлен по сроку, на границе 503 с `Retry-After`
    """Срок расчёта вышел: частичный ответ не нужен."""


def _ms_since(clock: Callable[[], float], started: float) -> int:
    return max(0, round((clock() - started) * 1000))


class PackCompareService:
    """Один на процесс: держит кэши, семафор тяжёлых расчётов и общие расчёты одинаковых запросов."""

    def __init__(
        self,
        outcomes: PackOutcomeService,
        atlases: PackAtlasService,
        *,
        limits: CompareLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._outcomes = outcomes
        self._atlases = atlases
        self._limits = limits or CompareLimits()
        self._clock = clock
        self._slots = asyncio.Semaphore(self._limits.concurrency)
        self._compared: LruCache[dict[str, Any]] = LruCache(self._limits.compare_entries)
        self._heavy: LruCache[dict[str, Any]] = LruCache(self._limits.heavy_entries, max_cost=self._limits.cache_bytes)
        self._inflight: dict[str, asyncio.Task[dict[str, Any]]] = {}

    # ── compare ──────────────────────────────────────────────────────────────

    async def compare(  # noqa: PLR0913 — путь версии, две стороны и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        left: Subject,
        right: Subject,
        *,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Сравнение двух результатов (`PackOutcomeCompare`). Стороны на одном состоянии (два набора вводных, два
        сценария) или на двух (`work_tree` против `head` и `base`). Сторона, чьё состояние недоступно:
        `diff_base_unavailable`; вводные, не подходящие версии стороны: `inputs_invalid` с полем `side`."""
        prep_l = await self._prepare(actor, workspace_id, pack, template, version, left)
        prep_r = await self._prepare(actor, workspace_id, pack, template, version, right)
        key = request_key(
            {
                "kind": "compare",
                "left": self._side_key(prep_l, left),
                "right": self._side_key(prep_r, right),
            }
        )
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        cached = self._compared.get(key)
        if cached is not None:
            return OutcomeReply(etag, cached)
        sides = (self._side(prep_l, left), self._side(prep_r, right))
        today = prep_l.today

        def work() -> Any:
            try:
                return compare_sides(sides[0], sides[1], today)
            except SideInputError as exc:
                return exc

        result = await self._outcomes.compute(work)
        if isinstance(result, SideInputError):
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid,
                field=result.field,
                value=result.value,
                reason=result.reason,
                side=result.side,
            )
        body = {
            "workspace_id": str(prep_l.ws.id),
            "pack": prep_l.ref.pack,
            "template": prep_l.ref.template,
            "version": prep_l.ref.version,
            **compare_body(result, left.state, right.state),
        }
        self._check_size(body)
        self._compared.put(key, body)
        return OutcomeReply(etag, body)

    def _prepare(  # noqa: PLR0913 — путь версии и сторона
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, subject: Subject
    ) -> Awaitable[PreparedVersion]:
        return self._outcomes.prepare(
            actor, workspace_id, pack, template, version, subject.state, subject.example, subject.scenario
        )

    def _side_key(self, prep: PreparedVersion, subject: Subject) -> str:
        return self._outcomes.key_of(
            prep, subject.state, kind="side", inputs=self._outcomes.merged_inputs(prep, subject.inputs)
        )

    def _side(self, prep: PreparedVersion, subject: Subject) -> Side:
        return Side(
            prep.source.desc.version,
            prep.example,
            self._outcomes.merged_inputs(prep, subject.inputs),
            prep.revision,
        )

    # ── impact ───────────────────────────────────────────────────────────────

    async def impact(  # noqa: PLR0913 — путь версии, база, выбор сценариев и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        *,
        base: BaseName = "base",
        scenarios: list[str] | None = None,
        include_atlas: bool = True,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """«До и после»: рабочее дерево против базы (`base`) или последнего коммита (`head`) по сценариям шаблона и,
        с `include_atlas`, по атласу (`PackOutcomeImpact`)."""
        after = await self._outcomes.prepare(actor, workspace_id, pack, template, version, "work_tree", None)
        before = await self._outcomes.prepare(actor, workspace_id, pack, template, version, base, None)
        files = after.source.scenarios
        names = select_scenario_files(files, scenarios)
        key = request_key(
            {
                "kind": "impact",
                "work_tree": self._outcomes.key_of(after, "work_tree", kind="impact"),
                "base": self._outcomes.key_of(before, base, kind="impact"),
                "scenarios": scenario_digests(files, names),
                "atlas": include_atlas,
            }
        )
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        parsed = parse_scenario_files(pack, template, files, names)

        async def build() -> dict[str, Any]:
            return await self._impact_body(
                actor, workspace_id, pack, template, version, base, before, after, parsed, include_atlas
            )

        return OutcomeReply(etag, await self._cached(key, build))

    async def _impact_body(  # noqa: PLR0913 — обе стороны, сценарии и атлас
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        base: BaseName,
        before: PreparedVersion,
        after: PreparedVersion,
        scenarios: Mapping[str, Scenario | str],
        include_atlas: bool,
    ) -> dict[str, Any]:
        old, new = _version_side(before), _version_side(after)
        today = after.today

        def work(check: Callable[[], None]) -> Any:
            return scenario_impacts(old, new, scenarios, today, labels=(base, "work_tree"), check=check)

        impacts = await self._limited(work)
        atlas = (
            await self._atlas_impact(actor, workspace_id, pack, template, version, base, before, after)
            if include_atlas
            else None
        )
        return {
            "workspace_id": str(after.ws.id),
            "pack": after.ref.pack,
            "template": after.ref.template,
            "version": after.ref.version,
            "base": base,
            "base_revision": before.revision,
            "work_tree_revision": after.revision,
            **impact_body(impacts, atlas),
        }

    async def _atlas_impact(  # noqa: PLR0913 — путь версии, база и обе стороны
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        base: BaseName,
        before: PreparedVersion,
        after: PreparedVersion,
    ) -> dict[str, int] | None:
        """Строки атласа «до и после»; None, если таблица одной из сторон шире предела атласа."""
        try:
            now = await self._atlases.atlas(actor, workspace_id, pack, template, version, "work_tree")
            was = await self._atlases.atlas(actor, workspace_id, pack, template, version, base)
        except PackStudioError as exc:
            if exc.code is PackStudioErrorCode.atlas_too_large:
                return None
            raise
        assert now.body is not None  # noqa: S101
        assert was.body is not None  # noqa: S101 — без If-None-Match тело всегда есть
        version_before, example, today = before.source.desc.version, before.example, after.today
        now_body, was_body = now.body, was.body

        def work(check: Callable[[], None]) -> dict[str, int]:
            return atlas_impact(now_body, was_body, version_before, example, today, check=check)

        return await self._limited(work)

    # ── matrix ───────────────────────────────────────────────────────────────

    async def matrix(  # noqa: PLR0913 — путь версии, состояние, выбор сценариев и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        *,
        state: OutcomeState = "work_tree",
        scenarios: list[str] | None = None,
        against: Literal["base"] | None = None,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Матрица «сценарии на разделы» (`PackOutcomeMatrix`): отпечаток, счётчик и статус клетки; с `against: base`
        у клетки ещё и отличие от вершины базовой ветки."""
        current = await self._outcomes.prepare(actor, workspace_id, pack, template, version, state, None)
        base = (
            await self._outcomes.prepare(actor, workspace_id, pack, template, version, "base", None)
            if against
            else None
        )
        files = current.source.scenarios
        names = select_scenario_files(files, scenarios)
        key = request_key(
            {
                "kind": "matrix",
                "state": self._outcomes.key_of(current, state, kind="matrix"),
                "base": self._outcomes.key_of(base, "base", kind="matrix") if base is not None else None,
                "scenarios": scenario_digests(files, names),
            }
        )
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        parsed = parse_scenario_files(pack, template, files, names)

        async def build() -> dict[str, Any]:
            side, base_side = _version_side(current), _version_side(base) if base is not None else None
            today = current.today

            def work(check: Callable[[], None]) -> Any:
                return matrix_rows(side, parsed, today, base=base_side, check=check)

            rows = await self._limited(work)
            return {
                "workspace_id": str(current.ws.id),
                "pack": current.ref.pack,
                "template": current.ref.template,
                "version": current.ref.version,
                "state": state,
                "revision": current.revision,
                **matrix_body(rows),
            }

        return OutcomeReply(etag, await self._cached(key, build))

    # ── общее ────────────────────────────────────────────────────────────────

    async def _cached(self, key: str, build: Callable[[], Coroutine[Any, Any, dict[str, Any]]]) -> dict[str, Any]:
        """Ответ из кэша либо расчёт, общий с одинаковыми одновременными запросами; размер проверяется до кэша."""
        cached = self._heavy.get(key)
        if cached is not None:
            return cached
        task = self._inflight.get(key)
        if task is None:
            task = spawn_detached(build(), name="pack-compare")
            self._inflight[key] = task
            task.add_done_callback(lambda done: self._done(key, done))
        body = await asyncio.shield(task)
        size = self._check_size(body)
        self._heavy.put(key, body, cost=size)
        return body

    def _done(self, key: str, done: asyncio.Task[dict[str, Any]]) -> None:
        self._inflight.pop(key, None)
        if not done.cancelled():
            done.exception()  # прочитано, чтобы брошенный расчёт не попал в журнал как «не полученный»

    def _check_size(self, body: Mapping[str, Any]) -> int:
        size = len(json.dumps(body, ensure_ascii=False))
        if size > self._limits.response_bytes:
            raise PackStudioError(PackStudioErrorCode.outcome_too_large, limit=self._limits.response_bytes, size=size)
        return size

    def _busy(self, reason: str) -> PackStudioError:
        return PackStudioError(
            PackStudioErrorCode.outcome_busy, reason=reason, retry_after_s=self._limits.retry_after_s
        )

    async def _limited[T](self, work: Callable[[Callable[[], None]], T]) -> T:
        """Тяжёлый расчёт в потоке под семафором и сроком; `work` получает проверку срока и зовёт её между расчётами."""
        deadline = self._clock() + self._limits.timeout_s

        def check() -> None:
            if self._clock() > deadline:
                raise _Deadline

        try:
            async with asyncio.timeout(self._limits.timeout_s):
                await self._slots.acquire()
        except TimeoutError:
            raise self._busy("overloaded") from None
        try:
            return await asyncio.to_thread(work, check)
        except _Deadline:
            raise self._busy("timeout") from None
        finally:
            self._slots.release()


def _version_side(prep: PreparedVersion) -> VersionSide:
    return VersionSide(prep.source.desc.version, tuple(examples_of(prep.source.desc)))


__all__ = ["BaseName", "CompareLimits", "PackCompareService", "Subject"]
