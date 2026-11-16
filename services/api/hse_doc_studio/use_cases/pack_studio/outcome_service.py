"""Результат версии шаблона по HTTP: словарь вводных и расчёт (template-studio-outcome.md, 4.2 и 4.6, срез O2).

Обвязка вокруг ядра `resolve` (`use_cases/pack_studio/outcome`): ничего не пишет и не меняет состояние. Вычислитель
чистый, поэтому всё, что ему нужно, собирается здесь.

- **Источник версии.** `work_tree`: рабочее дерево пространства, с несохранёнными правками (модель версии тем же
  разбором в отдельном процессе, что у предпросмотра; манифесты читаются с диска). `head` и `base`: последний коммит
  и вершина базовой ветки из git пространства без checkout; файлы версии читаются из хранилища (частичный клон
  догружает блобы тем же путём, что `workspace_git`), кладутся во временную папку и разбираются тем же процессом.
  Папка без git не имеет `head` и `base` (`diff_base_unavailable`), версии, которой нет в коммите, тоже.
- **Ключ и ETag.** Ответ зависит от пространства и версии, состояния и его источника (дайджест каталога или коммит),
  `revision` манифестов (`version.yaml`, `files/*/doc.yaml`, файл выбранного набора данных), дня, набора, вводных и
  `include`. ETag это хэш ключа: по `If-None-Match` ответ не считается вовсе (304).
- **Кэш.** LRU результатов и словарей вводных по ключу, LRU разобранных версий `head` и `base` по коммиту. Несохранённые
  правки учитываются сами: ключ `work_tree` несёт дайджест каталога и `revision`, а не коммит.
- **Предел расчёта.** `resolve` и словарь идут в отдельных потоках с таймаутом (по умолчанию 5 с) и защитой от
  перегрузки: рабочих потоков конечное число, очередь ограничена. Таймаут и переполнение это `outcome_busy` (503 с
  `Retry-After`). Поток, который не уложился, нельзя прервать: он занимает место до конца, поэтому следующие расчёты
  при залипшем не копятся, а получают отказ сразу.
- **Сценарии (срез O6).** Файлы `scenarios/*` шаблона читаются вместе с версией из того же состояния
  (`_Source.scenarios`: диск у `work_tree`, коммит у `head` и `base`). `scenario` запроса кладёт вводные сценария
  между умолчаниями и вводными запроса, дайджест файла входит в ключ и ETag. Список, запись и прогон сценариев:
  `scenario_service.py`, он берёт отсюда версию (`scenario_context`), чтение файлов (`read_scenarios`) и расчёт под
  тем же пределом (`compute`).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError
from hse_doc_studio.core.pack_studio.outcome.model import IncludeName
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.revision import example_file_names, is_manifest_path, revision_of
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    SCENARIOS_DIR,
    Scenario,
    ScenarioError,
    parse_scenario,
    scenario_file_name,
    version_matches,
)
from hse_doc_studio.core.pack_studio.outcome.serving import LruCache, etag_matches, etag_of, request_key
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VersionRef
from hse_doc_studio.core.pack_studio.preview import AUTO_NORMAL, PreviewExample, VersionDescription
from hse_doc_studio.core.pack_studio.protocols import (
    GitRevisionName,
    IPackPreviewRenderer,
    IPackWorkspaceFiles,
    IPackWorkspaceGit,
)
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.use_cases.pack_studio.outcome.dictionary import inputs_dictionary
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.preview import (
    PackPreviewService,
    default_example_of,
    examples_of,
    version_ref,
)
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

logger = structlog.get_logger()

OutcomeState = Literal["work_tree", "head", "base"]

# Через сколько секунд повторять запрос, не уложившийся в предел или отклонённый из-за перегрузки.
RETRY_AFTER_S = 2
# Манифест версии и файл набора данных больше этого в `revision` не идут (как манифесты дерева).
_MANIFEST_MAX_BYTES = 512 * 1024
_RESULT_CACHE_BYTES = 96 * 1024 * 1024
# Файл сценария больше этого не читается (запись сценария ограничена тем же).
SCENARIO_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class OutcomeLimits:
    # Предел одного расчёта и число одновременных; сверх `max_pending` (идущие плюс ждущие) запрос отклоняется.
    timeout_s: float = 5.0
    max_concurrent: int = 4
    max_pending: int = 8
    # LRU: результаты, словари вводных, разобранные версии `head` и `base`.
    cache_entries: int = 256
    cache_bytes: int = _RESULT_CACHE_BYTES
    dictionary_entries: int = 32
    snapshot_entries: int = 16
    # Пределы чтения версии из коммита (как у рабочего дерева).
    max_files: int = 20_000
    max_bytes: int = 268_435_456


@dataclass(frozen=True)
class OutcomeRequest:
    """Запрос расчёта: `inputs` поверх набора данных и умолчаний (раздел 4.3 дизайна)."""

    state: OutcomeState = "work_tree"
    scenario: str | None = None
    example: str | None = None
    inputs: Mapping[str, str] = field(default_factory=dict)
    include: frozenset[IncludeName] = frozenset()


@dataclass(frozen=True)
class OutcomeReply:
    """`body` None: у клиента уже есть этот ответ (`If-None-Match` совпал), отвечать 304."""

    etag: str
    body: dict[str, Any] | None


@dataclass(frozen=True)
class _Source:
    """Версия в выбранном состоянии: что считать и чем помечен её источник (ключ кэша)."""

    token: str
    desc: VersionDescription
    # Манифесты и наборы данных: `version.yaml`, `files/<документ>/doc.yaml`, `examples/<имя>`.
    texts: Mapping[str, bytes]
    # Файлы сценариев шаблона (`scenarios/<имя>`), вне каталога версии: имя файла -> содержимое (срез O6).
    scenarios: Mapping[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioUse:
    """Сценарий, вводные которого лежат между умолчаниями и вводными запроса: id, вводные и дайджест файла (он входит
    в ключ кэша и ETag, правка сценария меняет ответ)."""

    id: str
    inputs: Mapping[str, str]
    digest: str


@dataclass(frozen=True)
class _Prepared:
    ws: PackWorkspace
    ref: VersionRef
    source: _Source
    example: PreviewExample
    revision: str
    today: date
    scenario: ScenarioUse | None = None


@dataclass(frozen=True)
class ScenarioContext:
    """Версия шаблона в выбранном состоянии для прогона сценариев и записи снимка."""

    ws: PackWorkspace
    ref: VersionRef
    state: OutcomeState
    source: _Source
    today: date

    @property
    def revision(self) -> str:
        """Ревизия манифестов версии и всех наборов данных шаблона: сценарии выбирают наборы по-разному."""
        texts = {p: t for p, t in self.source.texts.items() if is_manifest_path(p) or p.startswith("examples/")}
        return revision_of(texts)

    @property
    def examples(self) -> tuple[PreviewExample, ...]:
        return examples_of(self.source.desc)

    @property
    def version(self) -> str:
        return self.ref.version


type PreparedVersion = _Prepared


def _now_today() -> date:
    return datetime.now(DISPLAY_ZONE).date()


def _busy(reason: str) -> PackStudioError:
    return PackStudioError(PackStudioErrorCode.outcome_busy, reason=reason, retry_after_s=RETRY_AFTER_S)


def _base_unavailable(reason: str) -> PackStudioError:
    return PackStudioError(PackStudioErrorCode.diff_base_unavailable, reason=reason)


class PackOutcomeService:
    """Один на процесс: держит кэши, пул потоков и счётчик идущих расчётов."""

    def __init__(  # noqa: PLR0913 — порты сценария и пределы
        self,
        workspaces: PackWorkspaceService,
        previews: PackPreviewService,
        renderer: IPackPreviewRenderer,
        files: IPackWorkspaceFiles,
        git: IPackWorkspaceGit,
        *,
        limits: OutcomeLimits | None = None,
        today: Callable[[], date] = _now_today,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._workspaces = workspaces
        self._previews = previews
        self._renderer = renderer
        self._files = files
        self._git = git
        self._limits = limits or OutcomeLimits()
        self._today = today
        self._clock = clock
        self._pool = ThreadPoolExecutor(max_workers=self._limits.max_concurrent, thread_name_prefix="outcome")
        self._pending = 0
        self._results: LruCache[dict[str, Any]] = LruCache(
            self._limits.cache_entries, max_cost=self._limits.cache_bytes
        )
        self._dictionaries: LruCache[dict[str, Any]] = LruCache(self._limits.dictionary_entries)
        self._snapshots: LruCache[_Source] = LruCache(self._limits.snapshot_entries)
        self._reading: dict[str, asyncio.Task[_Source]] = {}

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ── эндпоинты ────────────────────────────────────────────────────────────

    async def inputs(  # noqa: PLR0913 — путь версии, состояние и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        state: OutcomeState,
        *,
        scenario: str | None = None,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Вводные версии, наборы данных и умолчания (`PackOutcomeInputs`). С `scenario` словарь считается на
        наборе данных сценария (умолчания вводных зависят от набора); вводные сценария в словарь не входят, они
        приходят в `inputs` результата."""
        started = self._clock()
        prep = await self._prepare(actor, workspace_id, pack, template, version, state, None, scenario)
        key = request_key({**self._key_base(prep, state), "kind": "inputs"})
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        body = self._dictionaries.get(key)
        if body is None:
            desc, example, today, revision = prep.source.desc, prep.example, prep.today, prep.revision
            dictionary = await self._run(lambda: inputs_dictionary(desc.version, example, today, revision=revision))
            body = {
                "workspace_id": str(prep.ws.id),
                "pack": prep.ref.pack,
                "template": prep.ref.template,
                "version": prep.ref.version,
                "state": state,
                "revision": revision,
                "inputs": to_json(dictionary.inputs),
                "examples": [_example_json(e) for e in examples_of(desc)],
                "default_example": default_example_of(examples_of(desc)),
                "defaults": dict(dictionary.defaults),
            }
            self._dictionaries.put(key, body)
        logger.debug("pack studio outcome inputs", state=state, ms=_ms(self._clock() - started))
        return OutcomeReply(etag, body)

    async def outcome(  # noqa: PLR0913 — путь версии, запрос и условный запрос
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        request: OutcomeRequest,
        *,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Результат версии для вводных: разделы, трасса, отпечатки (`PackOutcome`)."""
        started = self._clock()
        prep = await self._prepare(
            actor, workspace_id, pack, template, version, request.state, request.example, request.scenario
        )
        key = request_key(
            {
                **self._key_base(prep, request.state),
                "kind": "outcome",
                "inputs": _merged_inputs(prep, request.inputs),
                "include": sorted(request.include),
            }
        )
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        cached = self._results.get(key)
        if cached is not None:
            return OutcomeReply(etag, {**cached, "elapsed_ms": _ms(self._clock() - started)})
        body = await self._calculate(prep, request)
        self._results.put(key, body, cost=len(json.dumps(body, ensure_ascii=False)))
        return OutcomeReply(etag, {**body, "elapsed_ms": _ms(self._clock() - started)})

    # ── сценарии (срез O6) ───────────────────────────────────────────────────

    async def read_scenarios(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, state: OutcomeState
    ) -> tuple[PackWorkspace, dict[str, bytes]]:
        """Файлы сценариев шаблона в состоянии версии: имя файла -> содержимое. `work_tree` читает диск, `head` и `base`
        коммит (версия для этого не нужна). Нет шаблона на диске: `version_not_found`."""
        ws, root = await self._workspaces.ready(actor, workspace_id)
        version_ref(pack, template, "0")  # имена пака и шаблона проходят ту же проверку пути
        template_dir = f"{pack}/{TEMPLATES_DIR}/{template}"
        if state == "work_tree":
            if not await asyncio.to_thread(self._files.is_dir, root, template_dir):
                raise PackStudioError(PackStudioErrorCode.version_not_found, version="")
            found = await asyncio.to_thread(
                self._files.template_files, root, pack, template, SCENARIOS_DIR, max_bytes=SCENARIO_MAX_BYTES
            )
            return ws, found
        sha = await self._revision_sha(ws, state)
        prefix = "" if ws.packs_path == "." else f"{ws.packs_path}/"
        files = await self._git.revision_files(
            self._workspaces.dirs_of(ws),
            self._workspaces.target_of(ws),
            sha=sha,
            prefixes=(f"{prefix}{template_dir}/{SCENARIOS_DIR}",),
            max_files=self._limits.max_files,
            max_bytes=self._limits.max_bytes,
        )
        unprefixed = {path.removeprefix(prefix): data for path, data in files.items() if path.startswith(prefix)}
        return ws, _scenario_texts(unprefixed, template_dir)

    async def scenario_context(  # noqa: PLR0913 — путь шаблона, состояние и выбор версии
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        state: OutcomeState,
        version: str | None = None,
        patterns: Sequence[str] = (),
    ) -> ScenarioContext:
        """Версия шаблона для прогона сценариев. Без `version` берётся старшая версия на диске пространства (подходящая
        под `patterns`, если они есть); в `head` и `base` она читается из коммита, там её может не быть
        (`diff_base_unavailable`, `new_version`)."""
        ws, root = await self._workspaces.ready(actor, workspace_id)
        if version is None:
            names = await asyncio.to_thread(self._files.template_versions, root, pack, template)
            candidates = [v for v in names if version_matches(patterns, v)]
            version = newest_version(candidates)
            if version is None:
                raise PackStudioError(PackStudioErrorCode.version_not_found, version="")
        ref = version_ref(pack, template, version)
        source = await self._source(ws, root, ref, state)
        return ScenarioContext(ws, ref, state, source, self._today())

    async def compute[T](self, work: Callable[[], T]) -> T:
        """Расчёт для сценариев тем же пределом времени и пулом, что результат; исключение вычислителя на манифесте,
        который лоадер принял, это `version_unreadable`, а не 500."""
        try:
            return await self._run(work)
        except PackStudioError:
            raise
        except Exception as exc:
            logger.warning("pack studio scenario calculation failed", exc_info=True)
            raise PackStudioError(
                PackStudioErrorCode.version_unreadable, reason=f"{type(exc).__name__}: {str(exc)[:200]}"
            ) from None

    # ── расчёт ───────────────────────────────────────────────────────────────

    async def _calculate(self, prep: _Prepared, request: OutcomeRequest) -> dict[str, Any]:
        version, example, today, revision = prep.source.desc.version, prep.example, prep.today, prep.revision
        include = request.include
        inputs = _merged_inputs(prep, request.inputs)

        def work() -> Any:
            try:
                return resolve(version, inputs, example, today, include=include, revision=revision)
            except OutcomeInputError as exc:
                return exc

        try:
            outcome = await self._run(work)
        except PackStudioError:
            raise
        except Exception as exc:
            # Манифест автора, который лоадер принял, а вычислитель нет: человек видит причину, а не 500.
            logger.warning("pack studio outcome failed", exc_info=True)
            raise PackStudioError(
                PackStudioErrorCode.version_unreadable, reason=f"{type(exc).__name__}: {str(exc)[:200]}"
            ) from None
        if isinstance(outcome, OutcomeInputError):
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field=outcome.field, value=outcome.value, reason=outcome.reason
            )
        return {
            "workspace_id": str(prep.ws.id),
            "pack": prep.ref.pack,
            "template": prep.ref.template,
            "version": prep.ref.version,
            "state": request.state,
            **to_json(outcome),
        }

    async def _run[T](self, work: Callable[[], T]) -> T:
        """Расчёт в потоке с пределом времени. Занято или не уложился: `outcome_busy`."""
        if self._pending >= self._limits.max_pending:
            raise _busy("overloaded")
        future = asyncio.get_running_loop().run_in_executor(self._pool, work)
        self._pending += 1
        future.add_done_callback(self._finished)
        try:
            return await asyncio.wait_for(asyncio.shield(future), self._limits.timeout_s)
        except TimeoutError:
            raise _busy("timeout") from None

    def _finished(self, future: asyncio.Future[Any]) -> None:
        # Место освобождается, когда поток закончил, а не когда запрос перестал ждать; исключение брошенного
        # расчёта прочитано, чтобы не попадать в журнал как «не полученное».
        self._pending -= 1
        if not future.cancelled():
            future.exception()

    # ── для других расчётов результата (атлас, срез O4) ──────────────────────

    async def prepare(  # noqa: PLR0913 — путь версии, состояние и набор данных
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        state: OutcomeState,
        example_id: str | None,
    ) -> PreparedVersion:
        """Версия в выбранном состоянии, набор данных, `revision` и день: то, из чего расчёты результата строят ключ
        и считают. Читает так же, как `inputs` и `outcome` (права, `head` и `base` из git, `diff_base_unavailable`)."""
        return await self._prepare(actor, workspace_id, pack, template, version, state, example_id)

    @classmethod
    def key_of(cls, prep: PreparedVersion, state: str, **extra: Any) -> str:
        """Ключ ответа расчёта по подготовленной версии: общая часть `_key_base` и то, что добавляет расчёт."""
        return request_key({**cls._key_base(prep, state), **extra})

    # ── источник версии ──────────────────────────────────────────────────────

    async def _prepare(  # noqa: PLR0913 — путь версии, состояние и набор данных
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        state: OutcomeState,
        example_id: str | None,
        scenario_id: str | None = None,
    ) -> _Prepared:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        source = await self._source(ws, root, ref, state)
        parsed = _read_scenario(source, scenario_id) if scenario_id is not None else None
        examples = examples_of(source.desc)
        if example_id:
            wanted = example_id
        elif parsed is not None:
            # Набор данных сценария; без него автонабор «Обычный»: результат сценария не зависит от файлов примеров.
            wanted = parsed[0].example or AUTO_NORMAL
        else:
            wanted = default_example_of(examples)
        example = next((e for e in examples if e.id == wanted), None)
        if example is None:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field="example", value=wanted, reason="unknown example"
            )
        if example.error is not None:
            raise PackStudioError(
                PackStudioErrorCode.inputs_invalid, field="example", value=wanted, reason=example.error
            )
        wanted_files = set(example_file_names(example.id))
        manifests = {
            path: text for path, text in source.texts.items() if is_manifest_path(path) or path in wanted_files
        }
        return _Prepared(ws, ref, source, example, revision_of(manifests), self._today(), parsed[1] if parsed else None)

    @staticmethod
    def _key_base(prep: _Prepared, state: str) -> dict[str, Any]:
        key: dict[str, Any] = {
            "workspace": str(prep.ws.id),
            "version": prep.ref.dir,
            "state": state,
            "source": prep.source.token,
            "revision": prep.revision,
            "today": prep.today.isoformat(),
            "example": prep.example.id,
        }
        if prep.scenario is not None:
            # Правка файла сценария меняет ответ, хотя манифесты и каталог версии те же.
            key["scenario"] = [prep.scenario.id, prep.scenario.digest]
        return key

    async def _work_tree(self, root: Path, ref: VersionRef) -> _Source:
        # Манифесты читаются первыми: нет каталога версии это `version_not_found`, а не сбой разбора.
        texts = await asyncio.to_thread(self._files.version_manifests, root, ref, max_bytes=_MANIFEST_MAX_BYTES)
        scenarios = await asyncio.to_thread(
            self._files.template_files, root, ref.pack, ref.template, SCENARIOS_DIR, max_bytes=SCENARIO_MAX_BYTES
        )
        desc, tree = await self._previews.describe_at(root, ref)
        return _Source(f"tree:{tree}", desc, texts, scenarios)

    async def _source(self, ws: PackWorkspace, root: Path, ref: VersionRef, state: OutcomeState) -> _Source:
        if state == "work_tree":
            return await self._work_tree(root, ref)
        return await self._revision(ws, ref, state)

    async def _revision(self, ws: PackWorkspace, ref: VersionRef, name: GitRevisionName) -> _Source:
        """`head` или `base`: коммит из git пространства, версия читается из его дерева."""
        sha = await self._revision_sha(ws, name)
        key = f"{ws.id}\0{sha}\0{ref.dir}"
        found = self._snapshots.get(key)
        if found is not None:
            return found
        task = self._reading.get(key)
        if task is None:
            task = spawn_detached(self._read_revision(ws, ref, sha))
            self._reading[key] = task
            task.add_done_callback(lambda done: self._read_done(key, done))
        source = await asyncio.shield(task)
        self._snapshots.put(key, source)
        return source

    async def _revision_sha(self, ws: PackWorkspace, name: GitRevisionName) -> str:
        """Коммит состояния `head` или `base`; папка без git и пространство без базы это `diff_base_unavailable`."""
        if ws.kind is not WorkspaceKind.git:
            raise _base_unavailable("no_git")
        if name == "base" and not ws.base_branch:
            raise _base_unavailable("no_base")
        sha = await self._git.revision_sha(self._workspaces.dirs_of(ws), name=name, base_branch=ws.base_branch or "")
        if sha is None:
            raise _base_unavailable("no_base" if name == "base" else "no_git")
        return sha

    def _read_done(self, key: str, done: asyncio.Task[_Source]) -> None:
        self._reading.pop(key, None)
        if not done.cancelled():
            done.exception()

    async def _read_revision(self, ws: PackWorkspace, ref: VersionRef, sha: str) -> _Source:
        prefix = "" if ws.packs_path == "." else f"{ws.packs_path}/"
        template_dir = f"{ref.pack}/{TEMPLATES_DIR}/{ref.template}"
        wanted: Sequence[str] = (
            f"{prefix}{ref.dir}",
            f"{prefix}{ref.pack}/pack.yaml",
            f"{prefix}{template_dir}/template.yaml",
            f"{prefix}{template_dir}/releases.yaml",
            f"{prefix}{template_dir}/examples",
            f"{prefix}{template_dir}/{SCENARIOS_DIR}",
        )
        found = await self._git.revision_files(
            self._workspaces.dirs_of(ws),
            self._workspaces.target_of(ws),
            sha=sha,
            prefixes=wanted,
            max_files=self._limits.max_files,
            max_bytes=self._limits.max_bytes,
        )
        files = {path.removeprefix(prefix): data for path, data in found.items() if path.startswith(prefix)}
        if f"{ref.dir}/version.yaml" not in files:
            raise _base_unavailable("new_version")
        desc = await self._renderer.describe_files(files, ref)
        return _Source(
            f"git:{sha}", desc, _manifest_texts(files, ref, template_dir), _scenario_texts(files, template_dir)
        )


def _manifest_texts(files: Mapping[str, bytes], ref: VersionRef, template_dir: str) -> dict[str, bytes]:
    """Манифесты версии и наборы данных из файлов коммита, под теми же ключами, что у рабочего дерева."""
    texts: dict[str, bytes] = {}
    for path, data in files.items():
        if len(data) > _MANIFEST_MAX_BYTES:
            continue
        if path.startswith(f"{ref.dir}/"):
            rel = path.removeprefix(f"{ref.dir}/")
            if is_manifest_path(rel):
                texts[rel] = data
        elif path.startswith(f"{template_dir}/examples/") and path.count("/") == template_dir.count("/") + 2:
            texts[path.removeprefix(f"{template_dir}/")] = data
    return texts


def _scenario_texts(files: Mapping[str, bytes], template_dir: str) -> dict[str, bytes]:
    """Файлы сценариев шаблона из файлов коммита: имя файла -> содержимое (вложенные папки не читаются)."""
    folder = f"{template_dir}/{SCENARIOS_DIR}/"
    return {
        path.removeprefix(folder): data
        for path, data in files.items()
        if path.startswith(folder) and "/" not in path.removeprefix(folder) and len(data) <= SCENARIO_MAX_BYTES
    }


def _read_scenario(source: _Source, scenario_id: str) -> tuple[Scenario, ScenarioUse]:
    """Сценарий из файлов источника: нет файла `scenario_not_found`, файл не по формату `scenario_invalid`."""
    try:
        name = scenario_file_name(scenario_id)
    except ScenarioError:
        raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id) from None
    data = source.scenarios.get(name)
    if data is None:
        raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id)
    try:
        scenario = parse_scenario(data.decode("utf-8"))
    except (ScenarioError, UnicodeDecodeError) as exc:
        reason = exc.reason if isinstance(exc, ScenarioError) else "the file is not UTF-8"
        raise PackStudioError(PackStudioErrorCode.scenario_invalid, scenario=scenario_id, reason=reason) from None
    return scenario, ScenarioUse(scenario_id, dict(scenario.inputs), hashlib.sha256(data).hexdigest()[:16])


def _merged_inputs(prep: _Prepared, request_inputs: Mapping[str, str]) -> dict[str, str]:
    """Вводные запроса поверх вводных сценария (умолчания версии и набора лежат под ними)."""
    scenario = dict(prep.scenario.inputs) if prep.scenario is not None else {}
    return {**scenario, **request_inputs}


def newest_version(versions: Sequence[str]) -> str | None:
    """Старшая версия по номеру (`2026.1.10` старше `2026.1.9`); номера не по схеме идут после разобранных."""
    keyed = [(parse_version_key(v), v) for v in versions]
    parsed = [(k, v) for k, v in keyed if k is not None]
    if parsed:
        return max(parsed)[1]
    return max(versions, default=None)


def _example_json(example: PreviewExample) -> dict[str, Any]:
    return {
        "id": example.id,
        "source": "file" if example.source == "file" else "auto",
        "label": dict(example.label) if example.label else None,
        "error": example.error,
        "defaults": dict(example.data.defaults) if example.data is not None else {},
    }


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))
