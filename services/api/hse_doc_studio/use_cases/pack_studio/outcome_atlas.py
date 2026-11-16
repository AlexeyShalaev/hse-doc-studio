"""Атлас результата для эндпоинта: состояние версии, пределы, кэш по `revision`, семафор и срок (раздел 4.4, 4.6).

Модуль лежит вне `outcome/`: там чистое ядро без часов и потоков (тест архитектуры).

Один на процесс. Расчёт идёт в потоке под семафором (две одновременных атласа на процесс), результат кэшируется по
(`state`, `revision`, набор данных, `pin`) на 16 атласов, анализ влияния отдельно по (`state`, `revision`, набор): смена
`pin` не повторяет перебор. Одинаковые одновременные запросы делят один расчёт. Срок (по умолчанию 20 с) проверяется
между расчётами комбинаций: поток остановится сам, запрос получит `AtlasBusy` (на границе 503 с `Retry-After`).

`ETag` строится из ключа кэша без расчёта: `If-None-Match` отвечает «не изменилось», не считая ничего.

Состояние `work_tree` (рабочее дерево, в том числе несохранённые правки) читается здесь; `head` и `base` читают из git
без checkout срез O2 и его чтение версии, до него они отвечают `diff_base_unavailable`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.atlas import ATLAS_MAX_ROWS, Atlas, AtlasCancelled, AtlasTooLarge
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.revision import revision_of
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.use_cases.pack_studio.outcome.atlas import build_atlas, example_defaults, validate_pins
from hse_doc_studio.use_cases.pack_studio.outcome.impact import (
    ImpactAnalysis,
    OutcomeEvaluator,
    analyze_impact,
)
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, VersionSource

MAX_PINS = 64
_DOC_MANIFEST = "doc.yaml"
_VERSION_MANIFEST = "version.yaml"


class AtlasBusy(Exception):  # noqa: N818 — не ошибка домена, а отказ по сроку: на границе 503 с `Retry-After`
    """Атлас не посчитан за срок или все места заняты; повторить через `retry_after_s`."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"atlas is busy, retry in {retry_after_s}s")
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class AtlasLimits:
    # Строк таблицы (выше `atlas_too_large`), срок расчёта, одновременных расчётов на процесс, размеры кэшей.
    max_rows: int = ATLAS_MAX_ROWS
    timeout_s: float = 20.0
    concurrency: int = 2
    cache_entries: int = 16
    analysis_entries: int = 8
    retry_after_s: int = 5


@dataclass(frozen=True)
class AtlasResult:
    """Ответ сервиса: `atlas` None, если `If-None-Match` совпал с `etag` (ничего не считали)."""

    state: str
    etag: str
    atlas: Atlas | None


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


def work_tree_revision(source: VersionSource, example: PreviewExample) -> str:
    """Ревизия рабочего дерева: тексты манифестов версии (`version.yaml`, `files/*/doc.yaml`), манифесты пака и шаблона
    и выбранный набор данных. TeX и прочие файлы в неё не входят: правка текста не должна сбрасывать атлас."""
    parts: dict[str, str | bytes] = {
        path: digest
        for path, digest in source.inputs.files.items()
        if path == _VERSION_MANIFEST or path.endswith(f"/{_DOC_MANIFEST}")
    }
    parts.update({f"extra:{i}": line for i, line in enumerate(source.inputs.extra)})
    raw = next((r for r in source.desc.examples if r.id == example.id), None)
    parts["example"] = json.dumps(
        [example.id, example.error, getattr(raw, "data", None)], sort_keys=True, ensure_ascii=False, default=str
    )
    return revision_of(parts)


def _etag(state: str, revision: str, example: str, pins: Mapping[str, str]) -> str:
    body = json.dumps([state, revision, example, sorted(pins.items())], ensure_ascii=False)
    return f'W/"atlas-{hashlib.sha256(body.encode()).hexdigest()[:20]}"'


class PackAtlasService:
    def __init__(
        self,
        previews: PackPreviewService,
        *,
        limits: AtlasLimits | None = None,
        today: Callable[[], date] = lambda: datetime.now(DISPLAY_ZONE).date(),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._previews = previews
        self._limits = limits or AtlasLimits()
        self._today = today
        self._clock = clock
        self._slots = asyncio.Semaphore(self._limits.concurrency)
        self._atlases: OrderedDict[tuple[object, ...], Atlas] = OrderedDict()
        self._analyses: OrderedDict[tuple[object, ...], ImpactAnalysis] = OrderedDict()
        self._inflight: dict[tuple[object, ...], asyncio.Task[Atlas]] = {}

    async def atlas(  # noqa: PLR0913 — путь версии, состояние, набор, закрепления и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        *,
        state: str = "work_tree",
        example: str | None = None,
        pins: Mapping[str, str] | None = None,
        if_none_match: str | None = None,
    ) -> AtlasResult:
        if state != "work_tree":
            # Чтение `head` и `base` из git приходит со срезом O2.
            raise PackStudioError(PackStudioErrorCode.diff_base_unavailable, reason="no_base")
        pins = dict(pins or {})
        source = await self._previews.source(actor, workspace_id, pack, template, version)
        chosen = self._example(source, example)
        revision = work_tree_revision(source, chosen)
        etag = _etag(state, revision, chosen.id, pins)
        if if_none_match is not None and etag in {tag.strip() for tag in if_none_match.split(",")}:
            return AtlasResult(state, etag, None)
        key = (state, revision, chosen.id, tuple(sorted(pins.items())))
        found = self._atlases.get(key)
        if found is None:
            found = await self._compute(key, source, chosen, pins, revision)
        else:
            self._atlases.move_to_end(key)
        return AtlasResult(state, etag, found)

    @staticmethod
    def _example(source: VersionSource, wanted: str | None) -> PreviewExample:
        chosen = wanted or source.default_example
        example = next((e for e in source.examples if e.id == chosen), None)
        if example is None:
            raise PackStudioError(PackStudioErrorCode.inputs_invalid, field="example", value=chosen, reason="unknown")
        if example.error is not None:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field="example", value=chosen, reason=example.error[:300]
            )
        return example

    async def _compute(
        self,
        key: tuple[object, ...],
        source: VersionSource,
        example: PreviewExample,
        pins: Mapping[str, str],
        revision: str,
    ) -> Atlas:
        # Закрепления проверяются до очереди: неверный запрос не занимает место.
        specs = input_specs(source.desc.version)
        try:
            validate_pins(specs, pins)
            normalize_inputs(specs, {}, example_defaults(example))
        except OutcomeInputError as exc:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field=exc.field, value=exc.value, reason=exc.reason
            ) from None
        task = self._inflight.get(key)
        if task is None:
            task = spawn_detached(self._run(key, source, example, pins, revision), name="pack-atlas")
            self._inflight[key] = task
            task.add_done_callback(lambda _t: self._inflight.pop(key, None))
        try:
            return await asyncio.shield(task)
        except AtlasTooLarge as exc:
            raise PackStudioError(PackStudioErrorCode.atlas_too_large, limit=exc.limit, rows=exc.rows) from None
        except (AtlasCancelled, TimeoutError):
            raise AtlasBusy(self._limits.retry_after_s) from None

    async def _run(
        self,
        key: tuple[object, ...],
        source: VersionSource,
        example: PreviewExample,
        pins: Mapping[str, str],
        revision: str,
    ) -> Atlas:
        deadline = self._clock() + self._limits.timeout_s

        def check() -> None:
            if self._clock() > deadline:
                raise AtlasCancelled

        analysis_key = (key[0], key[1], key[2])
        try:
            async with asyncio.timeout(self._limits.timeout_s):
                await self._slots.acquire()
        except TimeoutError:
            raise AtlasBusy(self._limits.retry_after_s) from None
        try:
            started = self._clock()
            loop = asyncio.get_running_loop()

            def keep(analysis: ImpactAnalysis) -> None:
                # Анализ дороже таблицы: он остаётся в кэше, даже если таблица не вышла (слишком большая, срок).
                loop.call_soon_threadsafe(
                    self._remember, self._analyses, analysis_key, analysis, self._limits.analysis_entries
                )

            atlas = await asyncio.to_thread(
                self._build, source, example, pins, revision, self._analyses.get(analysis_key), check, keep
            )
            atlas = replace(atlas, elapsed_ms=round((self._clock() - started) * 1000))
        finally:
            self._slots.release()
        self._remember(self._atlases, key, atlas, self._limits.cache_entries)
        return atlas

    def _build(  # noqa: PLR0913 — вход расчёта в потоке
        self,
        source: VersionSource,
        example: PreviewExample,
        pins: Mapping[str, str],
        revision: str,
        analysis: ImpactAnalysis | None,
        check: Callable[[], None],
        keep: Callable[[ImpactAnalysis], None],
    ) -> Atlas:
        version, today = source.desc.version, self._today()
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
            revision=revision,
            limit=self._limits.max_rows,
            analysis=analysis,
            evaluator=evaluator,
            check=check,
        )

    @staticmethod
    def _remember[V](cache: OrderedDict[tuple[object, ...], V], key: tuple[object, ...], value: V, size: int) -> None:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > size:
            cache.popitem(last=False)
