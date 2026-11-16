"""Линтер результата версии для эндпоинта: пределы, кэш, семафор и срок (раздел 4.6 и 6 дизайна результата, срез O8).

Модуль лежит вне `outcome/`: там чистое ядро без часов и потоков (тест архитектуры). Версию читает так же, как служба
результата (`PackOutcomeService.prepare`: права пространства, состояния `work_tree`, `head` и `base`, `revision`,
день и набор данных), ключ ответа и ETag строятся тем же `key_of` с дайджестами файлов сценариев.

Один на процесс. Расчёт (статические правила, атлас, результат с трассой в каждой его строке, прогон сценариев ради
покрытия) идёт в потоке под семафором (два на процесс), срок 30 с проверяется между расчётами строк: поток
останавливается сам, запрос получает `outcome_busy` (503 с `Retry-After`). Правила по файлам (Jinja) запускаются по
`jinja=true` и только на рабочем дереве, в отдельном процессе с пределами (`IPackJinjaProbe`). Результат кэшируется по
ключу; универсум правил (он нужен и покрытию прогона сценариев) отдельно по версии и её источнику.

`static` отдаёт только статические правила: `PackInsightService.lint` добавляет их к находкам `pack_lint` версии
(общий список «Проблемы»), они мгновенны.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.atlas import ATLAS_MAX_ROWS, AtlasCancelled, AtlasTooLarge
from hse_doc_studio.core.pack_studio.outcome.coverage import RuleUniverse, outcomes_universe
from hse_doc_studio.core.pack_studio.outcome.lint import LintFinding, LintSources, finding
from hse_doc_studio.core.pack_studio.outcome.lint_static import static_findings
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.scenarios import parse_scenario_files
from hse_doc_studio.core.pack_studio.outcome.serving import LruCache, etag_matches, etag_of
from hse_doc_studio.core.pack_studio.preview import PreviewExample, PreviewRenderError
from hse_doc_studio.core.pack_studio.protocols import IPackJinjaProbe
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.use_cases.pack_studio.outcome.lint import (
    OutcomeLint,
    lint_outcome,
    order_findings,
    scan_atlas,
)
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import coverage_universe, run_scenarios
from hse_doc_studio.use_cases.pack_studio.outcome_service import (
    OutcomeReply,
    OutcomeState,
    PackOutcomeService,
    PreparedVersion,
    ScenarioContext,
)
from hse_doc_studio.use_cases.pack_studio.preview import default_example_of, examples_of
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

logger = structlog.get_logger()

_MANIFESTS_PREFIX = "files/"


@dataclass(frozen=True)
class LintLimits:
    # Строк таблицы атласа (выше правила по атласу пропускаются), срок расчёта, одновременных расчётов на процесс,
    # размеры кэшей и через сколько секунд повторять отказанный запрос.
    max_rows: int = ATLAS_MAX_ROWS
    timeout_s: float = 30.0
    concurrency: int = 2
    cache_entries: int = 32
    universe_entries: int = 16
    retry_after_s: int = 5


def _texts(prep_texts: Mapping[str, bytes]) -> dict[str, str]:
    """Манифесты версии (`version.yaml`, `files/<документ>/doc.yaml`) текстом, ради строк находок."""
    return {
        name: data.decode("utf-8", errors="replace")
        for name, data in prep_texts.items()
        if name == "version.yaml" or (name.startswith(_MANIFESTS_PREFIX) and name.endswith("/doc.yaml"))
    }


def _scenario_digests(files: Mapping[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest()[:16] for name, data in sorted(files.items())}


class PackOutcomeLintService:
    def __init__(  # noqa: PLR0913 — службы, порт Jinja, пределы и часы
        self,
        outcomes: PackOutcomeService,
        workspaces: PackWorkspaceService,
        probe: IPackJinjaProbe | None = None,
        *,
        limits: LintLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._outcomes = outcomes
        self._workspaces = workspaces
        self._probe = probe
        self._limits = limits or LintLimits()
        self._clock = clock
        self._slots = asyncio.Semaphore(self._limits.concurrency)
        self._results: LruCache[dict[str, Any]] = LruCache(self._limits.cache_entries)
        self._universes: LruCache[RuleUniverse | None] = LruCache(self._limits.universe_entries)
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    # ── эндпоинт ─────────────────────────────────────────────────────────────

    async def lint(  # noqa: PLR0913 — путь версии, состояние, Jinja и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        state: OutcomeState,
        *,
        jinja: bool = False,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Находки линтера результата и покрытие правил сценариями (`PackOutcomeLint`); `body` None, если
        `If-None-Match` совпал с ключом. `jinja` добавляет правила по файлам (только рабочее дерево)."""
        started = self._clock()
        prep = await self._outcomes.prepare(actor, workspace_id, pack, template, version, state, None)
        run_jinja = jinja and state == "work_tree" and self._probe is not None
        key = self._outcomes.key_of(
            prep,
            state,
            kind="lint",
            jinja=run_jinja,
            scenarios=_scenario_digests(prep.source.scenarios),
        )
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        body = self._results.get(key)
        if body is None:
            body = await self._shared(
                key, lambda: self._lint_body(actor, prep, state, jinja=jinja, run_jinja=run_jinja)
            )
            self._results.put(key, body, cost=0)
        return OutcomeReply(etag, {**body, "elapsed_ms": max(0, round((self._clock() - started) * 1000))})

    async def static(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str
    ) -> tuple[LintFinding, ...]:
        """Статические правила версии рабочего дерева: мгновенно, для общего списка «Проблемы» рядом с `pack_lint`."""
        prep = await self._outcomes.prepare(actor, workspace_id, pack, template, version, "work_tree", None)
        sources = LintSources(prep.source.desc.version, _texts(prep.source.texts))
        return await asyncio.to_thread(static_findings, sources)

    # ── универсум для покрытия прогона сценариев ─────────────────────────────

    async def universe(self, ctx: ScenarioContext) -> RuleUniverse:
        """Универсум правил версии по строкам атласа для покрытия сценариев (общий кэш с линтером). Атлас больше
        предела: приближение по умолчаниям и переключению вводных по одной."""
        key = self._universe_key(ctx.ws.id, ctx.ref.dir, ctx.state, ctx.source.token, ctx.today)
        cached = self._universes.get(key)
        if cached is not None:
            return cached
        examples = ctx.examples
        version, today = ctx.source.desc.version, ctx.today
        example = _default_example(examples)

        def work(check: Callable[[], None]) -> RuleUniverse:
            try:
                return scan_atlas(version, example, today, limit=self._limits.max_rows, check=check).universe
            except AtlasTooLarge:
                return outcomes_universe(coverage_universe(version, examples, today))

        universe = await self._shared(key, lambda: self._compute(work))
        self._universes.put(key, universe)
        return universe

    # ── расчёт ───────────────────────────────────────────────────────────────

    @staticmethod
    def _universe_key(workspace: UUID, version_dir: str, state: str, token: str, today: date) -> str:
        return f"universe\0{workspace}\0{version_dir}\0{state}\0{token}\0{today.isoformat()}"

    async def _lint_body(
        self, actor: Actor, prep: PreparedVersion, state: str, *, jinja: bool, run_jinja: bool
    ) -> dict[str, Any]:
        version, example, today = prep.source.desc.version, prep.example, prep.today
        texts = _texts(prep.source.texts)
        scenarios = parse_scenario_files(prep.source.scenarios)
        limit = self._limits.max_rows
        examples = examples_of(prep.source.desc)

        def work(check: Callable[[], None]) -> tuple[OutcomeLint, Any]:
            lint = lint_outcome(version, texts, example, today, limit=limit, check=check)
            universe = lint.universe
            if universe is None:
                universe = outcomes_universe(coverage_universe(version, examples, today))
            return lint, run_scenarios(version, examples, scenarios, today, universe=universe).coverage

        lint, coverage = await self._compute(work)
        if lint.universe is not None:
            self._universes.put(
                self._universe_key(prep.ws.id, prep.ref.dir, state, prep.source.token, prep.today), lint.universe
            )
        findings = list(lint.findings)
        jinja_state = "not_run"
        if jinja and not run_jinja:
            jinja_state = "unavailable"
        elif run_jinja:
            jinja_state = "ran"
            findings.extend(await self._jinja(actor, prep))
        ordered = order_findings(tuple(findings))
        return {
            "workspace_id": str(prep.ws.id),
            "pack": prep.ref.pack,
            "template": prep.ref.template,
            "version": prep.ref.version,
            "state": state,
            "revision": prep.revision,
            "errors": sum(1 for f in ordered if f.severity == "error"),
            "warnings": sum(1 for f in ordered if f.severity == "warning"),
            "infos": sum(1 for f in ordered if f.severity == "info"),
            "findings": to_json(ordered),
            "coverage": to_json(coverage),
            "jinja": jinja_state,
            "atlas_skipped": lint.atlas_skipped,
        }

    async def _jinja(self, actor: Actor, prep: PreparedVersion) -> tuple[LintFinding, ...]:
        """Правила по файлам: отдельный процесс с пределами. Сбой процесса это находка, а не отказ ответа."""
        assert self._probe is not None  # noqa: S101 — проверено вызывающим
        _, root = await self._workspaces.ready(actor, prep.ws.id)
        try:
            return await self._probe.probe(root, prep.ref, prep.today)
        except PreviewRenderError as exc:
            logger.warning("pack studio jinja probe failed", reason=str(exc)[:200])
            return (
                finding(
                    "jinja-fail-open",
                    "warning",
                    f"Проверка шаблонов Jinja не завершилась: {str(exc)[:200]}",
                    "Повторите проверку; если она снова не укладывается в предел, упростите шаблоны.",
                    None,
                    None,
                ),
            )

    async def _compute[T](self, work: Callable[[Callable[[], None]], T]) -> T:
        """Расчёт в потоке под семафором и сроком; вышел срок или очередь полна: `outcome_busy`."""
        deadline = self._clock() + self._limits.timeout_s

        def check() -> None:
            if self._clock() > deadline:
                raise AtlasCancelled

        try:
            async with asyncio.timeout(self._limits.timeout_s):
                await self._slots.acquire()
        except TimeoutError:
            raise self._busy("overloaded") from None
        try:
            return await asyncio.to_thread(work, check)
        except AtlasCancelled:
            raise self._busy("timeout") from None
        except PackStudioError:
            raise
        except Exception as exc:
            logger.warning("pack studio lint failed", exc_info=True)
            raise PackStudioError(
                PackStudioErrorCode.version_unreadable, reason=f"{type(exc).__name__}: {str(exc)[:200]}"
            ) from None
        finally:
            self._slots.release()

    async def _shared[T](self, key: str, start: Callable[[], Coroutine[Any, Any, T]]) -> T:
        """Одинаковые одновременные запросы делят один расчёт."""
        task = self._inflight.get(key)
        if task is None:
            task = spawn_detached(start(), name="pack-lint")
            self._inflight[key] = task
            task.add_done_callback(lambda done: self._done(key, done))
        return await asyncio.shield(task)

    def _done(self, key: str, done: asyncio.Task[Any]) -> None:
        self._inflight.pop(key, None)
        if not done.cancelled():
            done.exception()  # прочитано, чтобы брошенный расчёт не попал в журнал как «не полученный»

    def _busy(self, reason: str) -> PackStudioError:
        return PackStudioError(
            PackStudioErrorCode.outcome_busy, reason=reason, retry_after_s=self._limits.retry_after_s
        )


def _default_example(examples: tuple[PreviewExample, ...]) -> PreviewExample:
    wanted = default_example_of(examples)
    return next(e for e in examples if e.id == wanted)


__all__ = ["LintLimits", "PackOutcomeLintService"]
