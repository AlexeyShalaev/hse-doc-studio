"""Предпросмотр версии шаблона на тестовых данных (docs/design/template-studio.md, раздел 6, срез T7).

Ход сборки (6.3): синтетический проект из набора данных и переключателей, рендер файлов пака в отдельном процессе
с пределами (раздел 9) в папку сборки, затем обычная задача `compile` через машину сборок (встроенный раннер
локально, очередь и раннеры на сервере). Готовый PDF ложится в кэш по ключу: дайджест входа документа, синтетический
проект и движок. Повтор той же комбинации ничего не собирает, правка одного документа пересобирает только его.

Пределы: у человека не больше `max_concurrent` идущих сборок (`preview_quota`), новая сборка того же слота
(пространство, версия, документ, набор, комбинация) отменяет прежнюю, а сборка с тем же ключом не запускается дважды.
На сервере минуты сборки идут в квоту сборок пользователя, как у сборок проекта.

Сборки живут в памяти процесса; запись и журнал лежат на диске. Сборка, которую процесс не довёл до конца (рестарт),
читается как `failed` с кодом `interrupted`.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
from hse_doc_studio.core.compile.errors import CompileSetupError
from hse_doc_studio.core.compile.failure import PDF_MISSING, CompileFailure, failure_log_block
from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.enums import CheckEngine, CompileStatus, EngineType
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.jobs.entities import CheckPlan, CompileJobPayload, CompileResult, JobResult, JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.documents import document_file_name, document_languages
from hse_doc_studio.core.pack_studio.outcome.inputs import (
    ANSWER_PREFIX,
    VARIANT_PREFIX,
    OutcomeInputError,
    input_specs,
    normalize_inputs,
)
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    SCENARIOS_DIR,
    Scenario,
    ScenarioError,
    parse_scenario,
    scenario_file_name,
)
from hse_doc_studio.core.pack_studio.paths import (
    TEMPLATES_DIR,
    VERSIONS_DIR,
    VersionRef,
    validate_rel_path,
    version_ref_of,
)
from hse_doc_studio.core.pack_studio.preview import (
    AUTO_NORMAL,
    PREVIEW_INTERRUPTED,
    RENDER_FAILED,
    ExampleFormatError,
    MaterializedDoc,
    MaterializeRequest,
    PreviewBuild,
    PreviewCheck,
    PreviewError,
    PreviewExample,
    PreviewInputError,
    PreviewRenderError,
    PreviewStatus,
    PreviewSwitch,
    SyntheticProject,
    VersionDescription,
    auto_examples,
    check_variant,
    document_digest,
    example_label,
    parse_example,
    pick_author,
    preview_cache_key,
    resolve_combination,
    switches_for,
    synthetic_project,
    team_authors,
)
from hse_doc_studio.core.pack_studio.protocols import (
    IPackPreviewRenderer,
    IPackWorkspaceFiles,
    IPreviewDispatcher,
    IPreviewStore,
)
from hse_doc_studio.core.services import CheckResolutionService, ProjectTemplateService
from hse_doc_studio.core.signatures.anchors import BuildAnchors, decode_anchors
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.core.value_objects import Author, CheckResult, ChecksOverride
from hse_doc_studio.use_cases.compile.compile_job_hooks import compile_failure
from hse_doc_studio.use_cases.pack_studio.synthetic_project import synthetic_core_project
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService, owner_of

logger = structlog.get_logger()

_NO_CHECKS = CheckPlan(rules_with_severity=(), ignored_rule_ids=frozenset(), needs_languagetool=False)
_DESCRIPTIONS_KEPT = 16
_PRUNE_EVERY_S = 600.0
MAX_DOCUMENTS_PER_REQUEST = 8
# Предел файла сценария, как у службы результата (`outcome_service.SCENARIO_MAX_BYTES`): ту службу отсюда не
# импортировать, она сама зависит от предпросмотра.
_SCENARIO_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class PreviewLimits:
    # Идущих сборок предпросмотра у одного человека (6.3, шаг 5).
    max_concurrent: int


@dataclass(frozen=True)
class PreviewOptions:
    """Что можно собрать в версии: документы, переключатели, наборы данных и комбинация по умолчанию."""

    pack_id: str
    template_id: str
    version_id: str
    documents: tuple[DocumentDefinition, ...]
    switches: tuple[PreviewSwitch, ...]
    examples: tuple[PreviewExample, ...]
    default_example: str
    combination: Mapping[str, str]
    # Языки редакций документов (id документа -> языки): те же, что `languages` документа в результате.
    languages: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class StartPreviewInput:
    documents: Sequence[str]
    example: str | None = None
    combination: Mapping[str, str] | None = None
    # Прогнать правила проверок версии на собранном документе (срез T14, «Проверить на предпросмотре»).
    checks: bool = False
    # Вариант документа (срез O9) у запроса с одним документом; None: вводная сценария, иначе первый.
    variant: str | None = None
    # Сценарий пака (`scenarios/<id>.yaml`): вводные и набор данных берутся из него, `combination` ложится поверх.
    scenario: str | None = None
    # Автор команды, чьи личные документы собирать: слаг или номер с единицы; None: первый автор.
    author: str | None = None


@dataclass(frozen=True)
class _Planned:
    build: PreviewBuild
    request: MaterializeRequest | None


@dataclass(frozen=True)
class _Resolved:
    """Запрос, приведённый к версии: набор, полная комбинация, синтетический проект, варианты из вводных сценария."""

    example: PreviewExample
    combo: dict[str, str]
    project: SyntheticProject
    variants: Mapping[str, str]
    scenario: Scenario | None = None


@dataclass(frozen=True)
class DocumentTarget:
    """Что собирается: определение документа, выбранный вариант (None: вариантов нет) и итоговое имя в пакете.

    `owner` слаг автора, чей это экземпляр (None: общий документ или одиночная работа); `first` ложно, если выбран
    экземпляр не первого автора: тогда автор входит в ключ кэша, а сборка по умолчанию делит ключ с прежними."""

    doc_def: DocumentDefinition
    variant: str | None
    file_name: str | None
    owner: str | None = None
    first: bool = True


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return datetime.now(DISPLAY_ZONE).date()


def version_ref(pack: str, template: str, version: str) -> VersionRef:
    ref = version_ref_of(validate_rel_path(f"{pack}/{TEMPLATES_DIR}/{template}/{VERSIONS_DIR}/{version}"))
    if ref is None or ref.rest:
        raise PackStudioError(PackStudioErrorCode.path_not_allowed)
    return ref


def _invalid(exc: PreviewInputError) -> PackStudioError:
    return PackStudioError(PackStudioErrorCode.preview_invalid, field=exc.field, value=exc.value, reason=exc.reason)


class PackPreviewService:
    """Один на процесс: держит идущие сборки, кэш разобранных моделей версий и счётчики пределов."""

    def __init__(  # noqa: PLR0913 — порты сценария и пределы
        self,
        workspaces: PackWorkspaceService,
        renderer: IPackPreviewRenderer,
        store: IPreviewStore,
        dispatcher: IPreviewDispatcher,
        *,
        limits: PreviewLimits,
        clock: Callable[[], datetime] = _now,
        today: Callable[[], date] = _today,
        files: IPackWorkspaceFiles | None = None,
    ) -> None:
        self._workspaces = workspaces
        # Чтение файлов сценариев шаблона; без него запрос со сценарием это `scenario_not_found`.
        self._files = files
        self._renderer = renderer
        self._store = store
        self._dispatcher = dispatcher
        self._limits = limits
        self._clock = clock
        self._today = today
        self._lock = asyncio.Lock()
        self._active: dict[UUID, PreviewBuild] = {}
        self._finishing: set[UUID] = set()
        self._submitted: set[UUID] = set()
        self._stopping: set[UUID] = set()
        self._warnings: dict[UUID, tuple[str, ...]] = {}
        # Id инстанса документа сборки: у личного документа команды это `<def>--<slug>`.
        self._doc_ids: dict[UUID, str] = {}
        # Правила проверок сборки «с проверками» (срез T14): решаются при постановке, как у сборки проекта.
        self._check_plans: dict[UUID, CheckPlan] = {}
        self._descriptions: OrderedDict[str, VersionDescription] = OrderedDict()
        self._pruned_at = 0.0
        # Рендер и постановка идут в фоне: запрос отвечает сразу, ход виден опросом.
        self._launches: set[asyncio.Task[None]] = set()

    # ── что можно собрать ───────────────────────────────────────────────────

    async def describe(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str
    ) -> VersionDescription:
        """Разобранная модель версии (в отдельном процессе, кэш по дайджесту входа): её читает и MCP `pack_read`."""
        _ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        return (await self.describe_at(root, ref))[0]

    async def describe_at(self, root: Path, ref: VersionRef) -> tuple[VersionDescription, str]:
        """Модель версии папки паков `root` и дайджест её каталога (по нему кэшируется модель): им пользуется и
        вычислитель результата, которому нужен тот же разбор в отдельном процессе."""
        tree = (await self._renderer.inputs(root, ref)).tree
        return await self._description(root, ref, tree), tree

    async def options(self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str) -> PreviewOptions:
        desc = await self.describe(actor, workspace_id, pack, template, version)
        examples = examples_of(desc)
        default = default_example_of(examples)
        chosen = next(e for e in examples if e.id == default)
        switches = switches_for(desc.version)
        defaults = chosen.data.defaults if chosen.data is not None else {}
        return PreviewOptions(
            pack_id=desc.pack_id,
            template_id=desc.template_id,
            version_id=desc.version.version,
            documents=desc.version.documents,
            switches=switches,
            examples=examples,
            default_example=default,
            combination=resolve_combination(switches, {}, defaults),
            languages={doc.id: document_languages(desc.version, doc) for doc in desc.version.documents},
        )

    # ── сборка ──────────────────────────────────────────────────────────────

    async def start(  # noqa: PLR0913 — путь версии и запрос
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str, inp: StartPreviewInput
    ) -> list[PreviewBuild]:
        ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        documents = list(dict.fromkeys(inp.documents))
        if not documents or len(documents) > MAX_DOCUMENTS_PER_REQUEST:
            raise _invalid(PreviewInputError("documents", str(len(documents)), "1..8 documents"))
        inputs = await self._renderer.inputs(root, ref)
        desc = await self._description(root, ref, inputs.tree)
        scenario = await self._scenario(root, ref, inp.scenario) if inp.scenario is not None else None
        try:
            if inp.variant is not None and len(documents) != 1:
                raise PreviewInputError("variant", inp.variant, "needs exactly one document")
            resolved = self._resolve(desc, inp, scenario)
            targets = document_targets(desc, documents, resolved.project, resolved.variants, inp.variant, inp.author)
        except PreviewInputError as exc:
            raise _invalid(exc) from exc
        example, combo, project = resolved.example, resolved.combo, resolved.project
        await self._maybe_prune()
        builds: list[PreviewBuild] = []
        for target in targets:
            doc_def = target.doc_def
            key = preview_cache_key(
                doc_digest=document_digest(inputs.files, desc.version, doc_def.id, inputs.extra),
                def_id=doc_def.id,
                project=project,
                engine=desc.version.engine_config.default.value,
                checks=inp.checks,
                variant=target.variant,
                author=None if target.first else target.owner,
            )
            draft = PreviewBuild(
                id=uuid4(),
                owner_id=owner_of(actor),
                workspace_id=ws.id,
                pack=ref.pack,
                template=ref.template,
                version=ref.version,
                document=doc_def.id,
                example=example.id,
                combination=combo,
                key=key,
                status=PreviewStatus.queued,
                cached=False,
                created_at=self._clock(),
                with_checks=inp.checks,
                variant=target.variant,
                file_name=target.file_name,
                scenario=inp.scenario,
                scenario_inputs=dict(resolved.scenario.inputs) if resolved.scenario is not None else {},
                author=target.owner,
                authors=team_authors(project),
            )
            planned = await self._plan(
                draft,
                MaterializeRequest(
                    desc.pack_id,
                    desc.template_id,
                    desc.version.version,
                    doc_def.id,
                    project,
                    draft.id,
                    target.variant,
                    target.owner,
                ),
            )
            if planned.request is not None:
                if inp.checks:
                    self._check_plans[planned.build.id] = check_plan(desc.version, doc_def)
                self._spawn(actor, root, ref, planned.build, planned.request)
            builds.append(self._active.get(planned.build.id) or await self._stored(planned.build))
        return builds

    async def synthetic(  # noqa: PLR0913 — путь версии, набор и комбинация
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        version: str,
        example: str | None,
        combination: Mapping[str, str] | None,
    ) -> tuple[VersionDescription, PreviewExample, dict[str, str], SyntheticProject]:
        """Модель версии (тот же разбор в отдельном процессе и кэш, что у сборки) и синтетический проект комбинации:
        «Маршрут в этой комбинации» (срез T13) считается на нём без сборки."""
        _ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        desc = await self._description(root, ref, (await self._renderer.inputs(root, ref)).tree)
        try:
            resolved = self._resolve(desc, StartPreviewInput((), example, combination), None)
        except PreviewInputError as exc:
            raise _invalid(exc) from exc
        return desc, resolved.example, resolved.combo, resolved.project

    async def wait_launched(self) -> None:
        """Дожидается фоновых рендеров и постановок (тесты и остановка приложения)."""
        while self._launches:
            await asyncio.gather(*list(self._launches), return_exceptions=True)

    async def get(self, actor: Actor, workspace_id: UUID, build_id: UUID) -> PreviewBuild:
        await self._workspaces.get(actor, workspace_id)
        build = self._active.get(build_id) or await asyncio.to_thread(self._store.load, build_id)
        if build is None or build.workspace_id != workspace_id or build.owner_id != owner_of(actor):
            raise PackStudioError(PackStudioErrorCode.preview_not_found)
        if build.id not in self._active and not build.status.is_terminal:
            # Процесс, который вёл сборку, перезапустился: довести её до конца некому.
            return replace(build, status=PreviewStatus.failed, error=PreviewError(PREVIEW_INTERRUPTED))
        return build

    async def pdf(self, actor: Actor, workspace_id: UUID, build_id: UUID) -> Path:
        build = await self.get(actor, workspace_id, build_id)
        path = self._store.pdf(build.key) if build.status is PreviewStatus.succeeded else None
        if path is None:
            raise PackStudioError(PackStudioErrorCode.preview_not_ready)
        return path

    async def anchors(self, actor: Actor, workspace_id: UUID, build_id: UUID) -> bytes:
        build = await self.get(actor, workspace_id, build_id)
        data = await asyncio.to_thread(self._store.anchors, build.key)
        if build.status is not PreviewStatus.succeeded or data is None:
            raise PackStudioError(PackStudioErrorCode.preview_not_ready)
        return data

    async def places_source(
        self, actor: Actor, workspace_id: UUID, build_id: UUID, ref: VersionRef
    ) -> tuple[PreviewBuild, BuildAnchors | None]:
        """Сборка версии `ref` для мест подписей (срез T9) и её якоря; None, если якорей нет или PDF не собран."""
        build = await self.get(actor, workspace_id, build_id)
        if (build.pack, build.template, build.version) != (ref.pack, ref.template, ref.version):
            raise PackStudioError(
                PackStudioErrorCode.preview_invalid,
                field="build_id",
                value=str(build_id),
                reason="the build is of another template version",
            )
        if build.status is not PreviewStatus.succeeded or not build.has_anchors:
            return build, None
        raw = await asyncio.to_thread(self._store.anchors, build.key)
        return build, decode_anchors(raw) if raw is not None else None

    async def log(self, actor: Actor, workspace_id: UUID, build_id: UUID) -> str:
        build = await self.get(actor, workspace_id, build_id)
        return await asyncio.to_thread(self._store.read_log, build) or ""

    async def cancel(self, actor: Actor, workspace_id: UUID, build_id: UUID) -> PreviewBuild:
        build = await self.get(actor, workspace_id, build_id)
        if build.status.is_terminal or build.id not in self._active:
            return build
        await self._stop(build)
        return self._active.get(build.id) or await self.get(actor, workspace_id, build_id)

    # ── шаги ────────────────────────────────────────────────────────────────

    async def _description(self, root: Path, ref: VersionRef, tree: str) -> VersionDescription:
        cache_key = f"{root}\0{ref.dir}\0{tree}"
        found = self._descriptions.get(cache_key)
        if found is not None:
            self._descriptions.move_to_end(cache_key)
            return found
        desc = await self._renderer.describe(root, ref)
        self._descriptions[cache_key] = desc
        while len(self._descriptions) > _DESCRIPTIONS_KEPT:
            self._descriptions.popitem(last=False)
        return desc

    async def _scenario(self, root: Path, ref: VersionRef, scenario_id: str) -> Scenario:
        """Сценарий пака из рабочего дерева пространства (его же собирает предпросмотр): нет файла это
        `scenario_not_found`, файл не по формату `scenario_invalid`, как у расчёта результата."""
        try:
            name = scenario_file_name(scenario_id)
        except ScenarioError:
            raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id) from None
        found = (
            await asyncio.to_thread(
                self._files.template_files, root, ref.pack, ref.template, SCENARIOS_DIR, max_bytes=_SCENARIO_MAX_BYTES
            )
            if self._files is not None
            else {}
        )
        data = found.get(name)
        if data is None:
            raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id)
        try:
            return parse_scenario(data.decode("utf-8"))
        except (ScenarioError, UnicodeDecodeError) as exc:
            reason = exc.reason if isinstance(exc, ScenarioError) else "the file is not UTF-8"
            raise PackStudioError(PackStudioErrorCode.scenario_invalid, scenario=scenario_id, reason=reason) from None

    def _resolve(self, desc: VersionDescription, inp: StartPreviewInput, scenario: Scenario | None) -> _Resolved:
        """Набор, полная комбинация и синтетический проект запроса.

        Без сценария комбинация это переключатели предпросмотра (не больше пяти полей анкеты). Со сценарием вводные
        считает ядро результата (`normalize_inputs` по всем вводным версии): вводные сценария, поверх них
        `combination`; так комбинация и варианты документов те же, что у результата по этому сценарию. Вводные
        ответов анкет на сборку не влияют, `variant.<документ>` становится вариантом документа, остальное это
        переключатели проекта."""
        examples = examples_of(desc)
        if inp.example:
            wanted = inp.example
        elif scenario is not None:
            # Как у расчёта результата: набор сценария, без него автонабор «Обычный» (файлы примеров не мешают).
            wanted = scenario.example or AUTO_NORMAL
        else:
            wanted = default_example_of(examples)
        example = next((e for e in examples if e.id == wanted), None)
        if example is None:
            raise PreviewInputError("example", wanted, "unknown example")
        if example.error is not None:
            raise PreviewInputError("example", wanted, example.error)
        defaults = example.data.defaults if example.data is not None else {}
        if scenario is None:
            combo = resolve_combination(switches_for(desc.version), inp.combination or {}, defaults)
            variants: dict[str, str] = {}
        else:
            full = _scenario_inputs(desc.version, scenario, inp, defaults)
            combo = {k: v for k, v in full.items() if not k.startswith((ANSWER_PREFIX, VARIANT_PREFIX))}
            variants = {k.removeprefix(VARIANT_PREFIX): v for k, v in full.items() if k.startswith(VARIANT_PREFIX)}
        return _Resolved(
            example, combo, synthetic_project(desc.version, example, combo, self._today()), variants, scenario
        )

    async def _plan(self, draft: PreviewBuild, request: MaterializeRequest) -> _Planned:
        """Кэш, сборка с тем же ключом, отмена прежней сборки слота и предел идущих: под одним замком."""
        async with self._lock:
            cached = await asyncio.to_thread(self._store.cached, draft.key)
            if cached is not None:
                done = replace(
                    draft,
                    status=PreviewStatus.succeeded,
                    cached=True,
                    started_at=draft.created_at,
                    finished_at=draft.created_at,
                    pages=cached.pages,
                    source_file=cached.source_file or None,
                    has_anchors=cached.has_anchors,
                    checks=cached.checks if draft.with_checks else None,
                )
                await asyncio.to_thread(self._store.save, done)
                return _Planned(done, None)
            live = [b for b in self._active.values() if b.id not in self._stopping]
            same = next((b for b in live if b.key == draft.key and b.owner_id == draft.owner_id), None)
            if same is not None:
                return _Planned(same, None)
            for previous in [b for b in live if b.slot == draft.slot]:
                await self._stop(previous)
            running = sum(1 for b in live if b.owner_id == draft.owner_id and b.id not in self._stopping)
            if running >= self._limits.max_concurrent:
                raise PackStudioError(PackStudioErrorCode.preview_quota, limit=self._limits.max_concurrent)
            self._active[draft.id] = draft
            await asyncio.to_thread(self._store.save, draft)
            return _Planned(draft, request)

    def _spawn(
        self, actor: Actor, root: Path, ref: VersionRef, build: PreviewBuild, request: MaterializeRequest
    ) -> None:
        # Задача создаётся в контексте запроса: язык интерфейса и актор остаются при ней.
        task = spawn_detached(self._launch(actor, root, ref, build, request))
        self._launches.add(task)
        task.add_done_callback(self._launches.discard)

    async def _launch(
        self, actor: Actor, root: Path, ref: VersionRef, build: PreviewBuild, request: MaterializeRequest
    ) -> None:
        try:
            await self._render_and_submit(actor, root, ref, build, request)
        except Exception as exc:  # noqa: BLE001 — фоновая задача: исход пишется в сборку, а не теряется
            logger.exception("pack preview: launch failed", build_id=str(build.id))
            await self._finish(build.id, PreviewStatus.failed, PreviewError(RENDER_FAILED, type(exc).__name__), "")

    async def _render_and_submit(
        self, actor: Actor, root: Path, ref: VersionRef, build: PreviewBuild, request: MaterializeRequest
    ) -> None:
        work = await asyncio.to_thread(self._store.work_dir, build.id)
        try:
            doc = await self._renderer.materialize(root, ref, request, work)
        except PreviewRenderError as exc:
            await self._finish(build.id, PreviewStatus.failed, PreviewError(RENDER_FAILED, str(exc)), f"[render] {exc}")
            return
        if build.id not in self._active:
            # Отменили, пока шёл рендер: папку уже убрал итог отмены, рендер мог её вернуть.
            await asyncio.to_thread(self._store.discard_work, build.id)
            return
        self._active[build.id] = replace(self._active[build.id], source_file=doc.source_file)
        self._warnings[build.id] = doc.warnings
        self._doc_ids[build.id] = doc.doc_id
        spec = _spec(actor, build, doc, work, self._check_plans.get(build.id, _NO_CHECKS))
        try:
            await self._dispatcher.preflight(spec)
        except (CompileSetupError, NoRunnerAvailableError) as exc:
            error = PreviewError(exc.code, str(exc))
            await self._finish(build.id, PreviewStatus.failed, error, f"[error] {exc}")
            return
        self._submitted.add(build.id)
        self._dispatcher.submit(spec, _PreviewHooks(self))

    async def _stop(self, build: PreviewBuild) -> None:
        self._stopping.add(build.id)
        if build.id in self._submitted and await self._dispatcher.cancel(build.id):
            return  # итог запишут хуки
        await self._finish(build.id, PreviewStatus.cancelled, None, "[cancelled]")

    async def _finish(
        self,
        build_id: UUID,
        status: PreviewStatus,
        error: PreviewError | None,
        log: str,
        *,
        pages: int | None = None,
        checks: tuple[PreviewCheck, ...] | None = None,
    ) -> None:
        # Сборка остаётся в `_active`, пока итог не записан на диск: иначе `get()` в этом окне не находит её ни в
        # памяти, ни завершённой в хранилище и отвечает «прервана».
        build = self._active.get(build_id)
        if build is None or build_id in self._finishing:
            return
        self._finishing.add(build_id)
        try:
            await self._finish_active(build, status, error, log, pages=pages, checks=checks)
        finally:
            self._active.pop(build_id, None)
            self._finishing.discard(build_id)
            self._check_plans.pop(build_id, None)

    async def _finish_active(
        self,
        build: PreviewBuild,
        status: PreviewStatus,
        error: PreviewError | None,
        log: str,
        *,
        pages: int | None,
        checks: tuple[PreviewCheck, ...] | None = None,
    ) -> None:
        build_id = build.id
        self._submitted.discard(build_id)
        self._stopping.discard(build_id)
        doc_id = self._doc_ids.pop(build_id, "")
        warnings = self._warnings.pop(build_id, ())
        text = "\n".join([*(f"[render] {w}" for w in warnings), log]).strip("\n") + "\n"
        has_anchors = False
        if status is PreviewStatus.succeeded:
            found = (checks or ()) if build.with_checks else None
            kept = await asyncio.to_thread(
                self._store.keep, build.key, build.id, build.source_file or "", doc_id, text, pages, found
            )
            if kept is None:
                status, error = PreviewStatus.failed, PreviewError(PDF_MISSING)
            else:
                has_anchors = kept.has_anchors
        done = replace(
            build,
            status=status,
            error=error,
            pages=pages,
            has_anchors=has_anchors,
            checks=((checks or ()) if build.with_checks else None) if status is PreviewStatus.succeeded else None,
            finished_at=self._clock(),
            started_at=build.started_at or self._clock(),
        )
        await asyncio.to_thread(self._store.save_log, build.id, text)
        await asyncio.to_thread(self._store.save, done)
        await asyncio.to_thread(self._store.discard_work, build.id)

    async def _stored(self, build: PreviewBuild) -> PreviewBuild:
        return await asyncio.to_thread(self._store.load, build.id) or build

    async def _maybe_prune(self) -> None:
        now = time.monotonic()
        if now - self._pruned_at < _PRUNE_EVERY_S:
            return
        self._pruned_at = now
        try:
            await asyncio.to_thread(self._store.prune)
        except OSError:
            logger.warning("pack preview: prune failed", exc_info=True)

    # ── для хуков ───────────────────────────────────────────────────────────

    async def on_started(self, build_id: UUID) -> bool:
        build = self._active.get(build_id)
        if build is None:
            return False
        running = replace(build, status=PreviewStatus.running, started_at=self._clock())
        self._active[build_id] = running
        await asyncio.to_thread(self._store.save, running)
        return True

    async def on_finished(self, build_id: UUID, result: JobResult, log: str) -> None:
        data = result.data if isinstance(result.data, CompileResult) else None
        if result.status is JobStatus.succeeded:
            checks = tuple(_check_of(c) for c in data.check_results) if data is not None else ()
            await self._finish(
                build_id, PreviewStatus.succeeded, None, log, pages=data.pages if data else None, checks=checks
            )
            return
        final = CompileStatus.cancelled if result.status is JobStatus.cancelled else CompileStatus.failure
        failure: CompileFailure = compile_failure(final, result, data)
        status = PreviewStatus.cancelled if final is CompileStatus.cancelled else PreviewStatus.failed
        block = failure_log_block(failure, current_interface_language())
        await self._finish(build_id, status, PreviewError(failure.code, failure.detail), f"{log.rstrip()}\n{block}")


class _PreviewHooks:
    """Хуки задачи `compile` сборки предпросмотра: запись проекта и журнал проекта не нужны, итог идёт в кэш."""

    def __init__(self, service: PackPreviewService) -> None:
        self._service = service

    async def on_started(self, spec: JobSpec) -> bool:
        return await self._service.on_started(spec.id)

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None:
        await self._service.on_finished(spec.id, result, log)


def check_plan(version: TemplateVersion, doc_def: DocumentDefinition) -> CheckPlan:
    """Правила версии для документа, как у сборки проекта без настроек проекта и человека (5.7): `applies_to`,
    `checks_version` и переопределения документа пака. LanguageTool не нужен: внешний движок на предпросмотре
    не гоняется, его правила пропускаются."""
    resolved = CheckResolutionService().resolve(
        rules=list(version.rules),
        doc_id=doc_def.id,
        version_cfg=version.checks_config,
        doc_definition_checks=doc_def.checks,
        project_override=ChecksOverride(),
        doc_override=ChecksOverride(),
        user_override=ChecksOverride(),
    )
    rules = tuple((rule, severity) for rule, severity in resolved if rule.engine is not CheckEngine.external)
    ignored = frozenset(version.checks_config.disabled) | frozenset(doc_def.checks.disabled)
    return CheckPlan(rules_with_severity=rules, ignored_rule_ids=ignored, needs_languagetool=False)


def _check_of(result: CheckResult) -> PreviewCheck:
    location = result.location
    return PreviewCheck(
        rule_id=result.rule_id,
        severity=result.severity.value,
        message=result.message,
        file=location.file if location is not None else None,
        line=location.line if location is not None else None,
    )


def _spec(actor: Actor, build: PreviewBuild, doc: MaterializedDoc, work: Path, plan: CheckPlan = _NO_CHECKS) -> JobSpec:
    payload = CompileJobPayload(
        doc_id=doc.doc_id,
        def_id=doc.def_id,
        source_file=doc.source_file,
        engine=EngineType(doc.engine),
        base_dir=doc.base_dir,
        needs_compile=doc.needs_compile,
        custom_mode=False,
        default_passes=doc.default_passes,
        check_plan=plan,
    )
    # Id задачи и «проекта» это id сборки: папка синтетического проекта называется так же (том предпросмотра).
    return JobSpec(
        id=build.id,
        kind=JobKind.compile,
        tags=job_tags(JobKind.compile, payload),
        project_id=build.id,
        actor=actor,
        locale=current_interface_language(),
        payload=payload,
        local_root=work,
    )


def examples_of(desc: VersionDescription) -> tuple[PreviewExample, ...]:
    files: list[PreviewExample] = []
    for raw in desc.examples:
        if raw.error is not None:
            files.append(PreviewExample(raw.id, "file", None, None, raw.error))
            continue
        try:
            files.append(PreviewExample(raw.id, "file", example_label(raw.data), parse_example(raw.data)))
        except ExampleFormatError as exc:
            files.append(PreviewExample(raw.id, "file", None, None, str(exc)))
    return (*files, *auto_examples(desc.version))


def default_example_of(examples: Sequence[PreviewExample]) -> str:
    return next((e.id for e in examples if e.source == "file" and e.error is None), AUTO_NORMAL)


def _scenario_inputs(
    version: TemplateVersion, scenario: Scenario, inp: StartPreviewInput, defaults: Mapping[str, str]
) -> dict[str, str]:
    """Полные вводные результата: вводные сценария, поверх них `combination` запроса (значения вне списка и
    незнакомые вводные это ошибка запроса, а у вводной сценария ошибка сценария)."""
    requested = inp.combination or {}
    try:
        return normalize_inputs(input_specs(version), {**scenario.inputs, **requested}, defaults)
    except OutcomeInputError as exc:
        if exc.field in requested:
            raise PreviewInputError(f"combination.{exc.field}", exc.value, exc.reason) from None
        raise PreviewInputError("scenario", inp.scenario or "", f"{exc.field}={exc.value!r}: {exc.reason}") from None


def _instance_of(instances: Sequence[Document], wanted: Author | None, doc_id: str) -> Document:
    """Экземпляр документа для сборки: у личного документа команды экземпляр автора `wanted`, иначе первый."""
    personal = any(d.owner is not None for d in instances)
    if wanted is None or wanted.slug is None or not personal:
        return instances[0]
    mine = next((d for d in instances if d.owner == wanted.slug), None)
    if mine is None:
        raise PreviewInputError("author", wanted.slug, f"this author has no document {doc_id!r}")
    return mine


def document_targets(
    desc: VersionDescription,
    documents: Sequence[str],
    project: SyntheticProject,
    variants: Mapping[str, str],
    variant: str | None = None,
    author: str | None = None,
) -> list[DocumentTarget]:
    """Документы запроса в проекте комбинации: есть ли документ, какой вариант и как называется файл.

    Документ есть, если движок создал его экземпляр (`_build_documents`, тот же проект, что у результата и у
    сборки). Вариант из запроса (`variant`) проверяется на язык проекта, иначе берётся вводная сценария (`variants`:
    документ -> вариант) и затем первый вариант, как `variants_of` результата. Имя файла считает общая функция
    результата (`document_file_name`). Нет документа или вариант не подходит: `PreviewInputError`.

    У личного документа команды экземпляр на каждого автора: без `author` собирается первый (первого автора), с
    `author` (слаг или номер с единицы, `pick_author`) экземпляр этого автора. Общему документу и одиночной работе
    выбор автора безразличен."""
    core = synthetic_core_project(desc.pack_id, desc.template_id, desc.version, project)
    templates = ProjectTemplateService()
    wanted = pick_author(project, author) if author is not None else None
    targets: list[DocumentTarget] = []
    for doc_id in documents:
        doc_def = next((d for d in desc.version.documents if d.id == doc_id), None)
        if doc_def is None:
            raise PreviewInputError("document", doc_id, "unknown document")
        instances = [d for d in core.documents if d.def_id == doc_id]
        if not instances:
            raise PreviewInputError("document", doc_id, "not in this combination")
        instance = _instance_of(instances, wanted, doc_id)
        chosen: str | None = None
        if variant is not None:
            check_variant(doc_def, variant, project.lang.value)
            chosen = variant
        elif doc_def.variants:
            chosen = variants.get(doc_id) or doc_def.variants[0].id
        instance.chosen_variant = chosen
        name = document_file_name(core, doc_def, instance, project.lang.value, templates)
        targets.append(DocumentTarget(doc_def, chosen, name, instance.owner, instance is instances[0]))
    return targets
