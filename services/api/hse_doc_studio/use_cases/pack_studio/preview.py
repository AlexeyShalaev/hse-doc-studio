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
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import DocumentDefinition
from hse_doc_studio.core.compile.errors import CompileSetupError
from hse_doc_studio.core.compile.failure import PDF_MISSING, CompileFailure, failure_log_block
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.jobs.entities import CheckPlan, CompileJobPayload, CompileResult, JobResult, JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
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
    PreviewError,
    PreviewExample,
    PreviewInputError,
    PreviewRenderError,
    PreviewStatus,
    PreviewSwitch,
    SyntheticProject,
    VersionDescription,
    auto_examples,
    document_digest,
    document_present,
    example_label,
    parse_example,
    preview_cache_key,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.core.pack_studio.protocols import IPackPreviewRenderer, IPreviewDispatcher, IPreviewStore
from hse_doc_studio.core.signatures.anchors import BuildAnchors, decode_anchors
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.use_cases.compile.compile_job_hooks import compile_failure
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService, owner_of

logger = structlog.get_logger()

_NO_CHECKS = CheckPlan(rules_with_severity=(), ignored_rule_ids=frozenset(), needs_languagetool=False)
_DESCRIPTIONS_KEPT = 16
_PRUNE_EVERY_S = 600.0
MAX_DOCUMENTS_PER_REQUEST = 8


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


@dataclass(frozen=True)
class StartPreviewInput:
    documents: Sequence[str]
    example: str | None = None
    combination: Mapping[str, str] | None = None


@dataclass(frozen=True)
class _Planned:
    build: PreviewBuild
    request: MaterializeRequest | None


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
    ) -> None:
        self._workspaces = workspaces
        self._renderer = renderer
        self._store = store
        self._dispatcher = dispatcher
        self._limits = limits
        self._clock = clock
        self._today = today
        self._lock = asyncio.Lock()
        self._active: dict[UUID, PreviewBuild] = {}
        self._submitted: set[UUID] = set()
        self._stopping: set[UUID] = set()
        # Сборки, чей итог сейчас записывается: повторный итог (отмена вдогонку) не пишется дважды.
        self._finishing: set[UUID] = set()
        self._warnings: dict[UUID, tuple[str, ...]] = {}
        # Id инстанса документа сборки: у личного документа команды это `<def>--<slug>`.
        self._doc_ids: dict[UUID, str] = {}
        self._descriptions: OrderedDict[str, VersionDescription] = OrderedDict()
        self._pruned_at = 0.0
        # Рендер и постановка идут в фоне: запрос отвечает сразу, ход виден опросом.
        self._launches: set[asyncio.Task[None]] = set()

    # ── что можно собрать ───────────────────────────────────────────────────

    async def options(self, actor: Actor, workspace_id: UUID, pack: str, template: str, version: str) -> PreviewOptions:
        _ws, root = await self._workspaces.ready(actor, workspace_id)
        ref = version_ref(pack, template, version)
        desc = await self._description(root, ref, (await self._renderer.inputs(root, ref)).tree)
        examples = _examples(desc)
        default = _default_example(examples)
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
        try:
            example, combo, project = self._project(desc, inp)
            defs = [_document(desc, doc_id, project) for doc_id in documents]
        except PreviewInputError as exc:
            raise _invalid(exc) from exc
        await self._maybe_prune()
        builds: list[PreviewBuild] = []
        for doc_def in defs:
            key = preview_cache_key(
                doc_digest=document_digest(inputs.files, desc.version, doc_def.id, inputs.extra),
                def_id=doc_def.id,
                project=project,
                engine=desc.version.engine_config.default.value,
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
            )
            planned = await self._plan(
                draft,
                MaterializeRequest(desc.pack_id, desc.template_id, desc.version.version, doc_def.id, project, draft.id),
            )
            if planned.request is not None:
                self._spawn(actor, root, ref, planned.build, planned.request)
            builds.append(self._active.get(planned.build.id) or await self._stored(planned.build))
        return builds

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

    def _project(
        self, desc: VersionDescription, inp: StartPreviewInput
    ) -> tuple[PreviewExample, dict[str, str], SyntheticProject]:
        examples = _examples(desc)
        wanted = inp.example or _default_example(examples)
        example = next((e for e in examples if e.id == wanted), None)
        if example is None:
            raise PreviewInputError("example", wanted, "unknown example")
        if example.error is not None:
            raise PreviewInputError("example", wanted, example.error)
        defaults = example.data.defaults if example.data is not None else {}
        combo = resolve_combination(switches_for(desc.version), inp.combination or {}, defaults)
        return example, combo, synthetic_project(desc.version, example, combo, self._today())

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
        spec = _spec(actor, build, doc, work)
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
    ) -> None:
        # Сборка остаётся среди идущих, пока её итог не записан: иначе опрос в этот промежуток не нашёл бы её
        # ни в памяти, ни в хранилище с итогом и прочитал бы как прерванную рестартом (`interrupted`).
        build = self._active.get(build_id)
        if build is None or build_id in self._finishing:
            return
        self._finishing.add(build_id)
        self._submitted.discard(build_id)
        self._stopping.discard(build_id)
        doc_id = self._doc_ids.pop(build_id, "")
        warnings = self._warnings.pop(build_id, ())
        try:
            await self._record(build, status, error, log, doc_id=doc_id, warnings=warnings, pages=pages)
        finally:
            self._active.pop(build_id, None)
            self._finishing.discard(build_id)

    async def _record(  # noqa: PLR0913 — итог сборки и что к нему приложить
        self,
        build: PreviewBuild,
        status: PreviewStatus,
        error: PreviewError | None,
        log: str,
        *,
        doc_id: str,
        warnings: tuple[str, ...],
        pages: int | None,
    ) -> None:
        text = "\n".join([*(f"[render] {w}" for w in warnings), log]).strip("\n") + "\n"
        has_anchors = False
        if status is PreviewStatus.succeeded:
            kept = await asyncio.to_thread(
                self._store.keep, build.key, build.id, build.source_file or "", doc_id, text, pages
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
            await self._finish(build_id, PreviewStatus.succeeded, None, log, pages=data.pages if data else None)
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


def _spec(actor: Actor, build: PreviewBuild, doc: MaterializedDoc, work: Path) -> JobSpec:
    payload = CompileJobPayload(
        doc_id=doc.doc_id,
        def_id=doc.def_id,
        source_file=doc.source_file,
        engine=EngineType(doc.engine),
        base_dir=doc.base_dir,
        needs_compile=doc.needs_compile,
        custom_mode=False,
        default_passes=doc.default_passes,
        check_plan=_NO_CHECKS,
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


def _examples(desc: VersionDescription) -> tuple[PreviewExample, ...]:
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


def _default_example(examples: Sequence[PreviewExample]) -> str:
    return next((e.id for e in examples if e.source == "file" and e.error is None), AUTO_NORMAL)


def _document(desc: VersionDescription, doc_id: str, project: SyntheticProject) -> DocumentDefinition:
    doc_def = next((d for d in desc.version.documents if d.id == doc_id), None)
    if doc_def is None:
        raise PreviewInputError("document", doc_id, "unknown document")
    if not document_present(doc_def, project):
        raise PreviewInputError("document", doc_id, "not in this combination")
    return doc_def
