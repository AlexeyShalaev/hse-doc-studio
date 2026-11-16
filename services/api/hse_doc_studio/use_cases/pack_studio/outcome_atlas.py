"""Атлас результата для эндпоинта: пределы, кэш, семафор и срок (раздел 4.4 и 4.6 дизайна результата, срез O4).

Модуль лежит вне `outcome/`: там чистое ядро без часов и потоков (тест архитектуры). Версию читает так же, как служба
результата (`PackOutcomeService.prepare`, срез O2): права пространства, состояния `work_tree`, `head` и `base`,
`revision` манифестов, день и набор данных; ключ ответа и ETag строятся по тем же правилам
(`core/pack_studio/outcome/serving.py`).

Один на процесс. Расчёт идёт в потоке под семафором (два атласа одновременно на процесс), срок 20 с проверяется между
расчётами комбинаций: поток останавливается сам, запрос получает `outcome_busy` (503 с `Retry-After`). Результат
кэшируется по ключу на 16 атласов, анализ влияния отдельно (он дороже таблицы и от `pin` не зависит): смена `pin`
его не повторяет. Одинаковые одновременные запросы делят один расчёт. ETag считается из ключа без расчёта:
`If-None-Match` отвечает «не изменилось», ничего не считая.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.atlas import ATLAS_MAX_ROWS, Atlas, AtlasCancelled, AtlasTooLarge
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.serving import LruCache, etag_matches, etag_of
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.use_cases.pack_studio.outcome.atlas import build_atlas, example_defaults, validate_pins
from hse_doc_studio.use_cases.pack_studio.outcome.impact import ImpactAnalysis, OutcomeEvaluator, analyze_impact
from hse_doc_studio.use_cases.pack_studio.outcome_service import (
    OutcomeReply,
    OutcomeState,
    PackOutcomeService,
    PreparedVersion,
)

MAX_PINS = 64
# Атлас ВКР в JSON около 1 МиБ: кэш держит и число записей, и размер.
_CACHE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class AtlasLimits:
    # Строк таблицы (выше `atlas_too_large`), срок расчёта, одновременных расчётов на процесс, размеры кэшей.
    max_rows: int = ATLAS_MAX_ROWS
    timeout_s: float = 20.0
    concurrency: int = 2
    cache_entries: int = 16
    cache_bytes: int = _CACHE_BYTES
    analysis_entries: int = 8
    retry_after_s: int = 5


def parse_pins(raw: Sequence[str]) -> dict[str, str]:
    """`pin=<вводная>:<значение>`: по первому двоеточию (в значении оно может быть). Повтор вводной это ошибка."""
    if len(raw) > MAX_PINS:
        raise PackStudioError(PackStudioErrorCode.inputs_invalid, field="pin", value=str(len(raw)), reason="too many")
    pins: dict[str, str] = {}
    for item in raw:
        input_id, sep, value = item.partition(":")
        if not sep or not input_id:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field="pin", value=item[:128], reason="expected <input>:<value>"
            )
        if input_id in pins:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field=input_id, value=value[:128], reason="pinned twice"
            )
        pins[input_id] = value
    return pins


class PackAtlasService:
    def __init__(
        self,
        outcomes: PackOutcomeService,
        *,
        limits: AtlasLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._outcomes = outcomes
        self._limits = limits or AtlasLimits()
        self._clock = clock
        self._slots = asyncio.Semaphore(self._limits.concurrency)
        self._atlases: LruCache[dict[str, object]] = LruCache(
            self._limits.cache_entries, max_cost=self._limits.cache_bytes
        )
        self._analyses: LruCache[ImpactAnalysis] = LruCache(self._limits.analysis_entries)
        self._inflight: dict[str, asyncio.Task[Atlas]] = {}

    async def atlas(  # noqa: PLR0913 — путь версии, состояние, набор, закрепления и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        state: OutcomeState,
        *,
        example: str | None = None,
        scenario: str | None = None,
        pins: Mapping[str, str] | None = None,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Таблица исходов версии (`PackOutcomeAtlas`); `body` None, если `If-None-Match` совпал с ключом. С `scenario`
        набор данных берётся у сценария, а его вводные становятся основой таблицы: у измерений `default` и остальные
        вводные это значения сценария, а не умолчания набора. Дайджест файла сценария входит в ключ и ETag."""
        started = self._clock()
        pins = dict(pins or {})
        prep = await self._outcomes.prepare(actor, workspace_id, pack, template, version, state, example, scenario)
        prep = self._on_scenario(prep)
        key = self._outcomes.key_of(prep, state, kind="atlas", pins=sorted(pins.items()))
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        body = self._atlases.get(key)
        if body is None:
            self._validate(prep, pins)
            atlas = await self._compute(key, state, prep, pins)
            body = {
                "workspace_id": str(prep.ws.id),
                "pack": prep.ref.pack,
                "template": prep.ref.template,
                "version": prep.ref.version,
                "state": state,
                **to_json(atlas),
            }
            self._atlases.put(key, body, cost=len(json.dumps(body, ensure_ascii=False)))
        return OutcomeReply(etag, {**body, "elapsed_ms": max(0, round((self._clock() - started) * 1000))})

    @staticmethod
    def _on_scenario(prep: PreparedVersion) -> PreparedVersion:
        """Вводные сценария как умолчания набора данных расчёта; не подходящие версии это `inputs_invalid`."""
        if prep.scenario is None:
            return prep
        try:
            normalize_inputs(input_specs(prep.source.desc.version), prep.scenario.inputs)
        except OutcomeInputError as exc:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field=exc.field, value=exc.value, reason=exc.reason
            ) from None
        data = prep.example.data
        if data is None:
            return prep
        merged = replace(data, defaults={**data.defaults, **prep.scenario.inputs})
        return replace(prep, example=replace(prep.example, data=merged))

    @staticmethod
    def _validate(prep: PreparedVersion, pins: Mapping[str, str]) -> None:
        """Закрепления проверяются до очереди: неверный запрос не занимает место и не ждёт."""
        try:
            validate_pins(input_specs(prep.source.desc.version), pins)
        except OutcomeInputError as exc:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field=exc.field, value=exc.value, reason=exc.reason
            ) from None

    async def _compute(self, key: str, state: str, prep: PreparedVersion, pins: Mapping[str, str]) -> Atlas:
        task = self._inflight.get(key)
        if task is None:
            task = spawn_detached(self._run(state, prep, pins), name="pack-atlas")
            self._inflight[key] = task
            task.add_done_callback(lambda done: self._done(key, done))
        try:
            return await asyncio.shield(task)
        except AtlasTooLarge as exc:
            raise PackStudioError(PackStudioErrorCode.atlas_too_large, limit=exc.limit, rows=exc.rows) from None
        except AtlasCancelled:
            raise self._busy("timeout") from None

    def _done(self, key: str, done: asyncio.Task[Atlas]) -> None:
        self._inflight.pop(key, None)
        if not done.cancelled():
            done.exception()  # прочитано, чтобы брошенный расчёт не попал в журнал как «не полученный»

    def _busy(self, reason: str) -> PackStudioError:
        return PackStudioError(
            PackStudioErrorCode.outcome_busy, reason=reason, retry_after_s=self._limits.retry_after_s
        )

    async def _run(self, state: str, prep: PreparedVersion, pins: Mapping[str, str]) -> Atlas:
        deadline = self._clock() + self._limits.timeout_s

        def check() -> None:
            if self._clock() > deadline:
                raise AtlasCancelled

        try:
            async with asyncio.timeout(self._limits.timeout_s):
                await self._slots.acquire()
        except TimeoutError:
            raise self._busy("overloaded") from None
        analysis_key = self._outcomes.key_of(prep, state, kind="atlas-analysis")
        loop = asyncio.get_running_loop()
        try:
            started = self._clock()

            def keep(analysis: ImpactAnalysis) -> None:
                # Анализ дороже таблицы: он остаётся в кэше, даже если таблица не вышла (слишком большая, срок).
                loop.call_soon_threadsafe(self._analyses.put, analysis_key, analysis)

            known = self._analyses.get(analysis_key)
            atlas = await asyncio.to_thread(self._build, prep, pins, known, check, keep)
        finally:
            self._slots.release()
        return replace(atlas, elapsed_ms=max(0, round((self._clock() - started) * 1000)))

    def _build(  # noqa: PLR0913 — вход расчёта в потоке
        self,
        prep: PreparedVersion,
        pins: Mapping[str, str],
        analysis: ImpactAnalysis | None,
        check: Callable[[], None],
        keep: Callable[[ImpactAnalysis], None],
    ) -> Atlas:
        version, example, today = prep.source.desc.version, prep.example, prep.today
        evaluator = None
        if analysis is None:
            specs = input_specs(version)
            defaults = normalize_inputs(specs, {}, example_defaults(example))
            evaluator = OutcomeEvaluator(version, specs, example, today, check=check)
            analysis = analyze_impact(evaluator, specs, defaults)
            keep(analysis)
        return build_atlas(
            version,
            example,
            today,
            pins=pins,
            revision=prep.revision,
            limit=self._limits.max_rows,
            analysis=analysis,
            evaluator=evaluator,
            check=check,
        )
