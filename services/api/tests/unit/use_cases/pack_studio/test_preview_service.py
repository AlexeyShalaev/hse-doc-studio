"""Сценарий предпросмотра: кэш, сборка с тем же ключом, отмена прежней сборки слота, предел идущих, рестарт.

Рендер и диспетчер подменены: здесь проверяется ход сборки, а не песочница и latexmk.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.compile.errors import ImageMissingError
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.preview import (
    MaterializedDoc,
    MaterializeRequest,
    PreviewInputs,
    PreviewRenderError,
    PreviewStatus,
    VersionDescription,
)
from hse_doc_studio.infra.pack_studio.preview_store import FsPreviewStore
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewLimits, StartPreviewInput

ACTOR = Actor.local()
WS = uuid4()

_VERSION = """\
id: "1.0.0"
langs: [ru]
documents:
  - { id: report, name: { ru: "Отчёт" }, source_file: report/report.tex, output_file: report/report.pdf }
  - { id: memo, name: { ru: "Записка" }, source_file: memo/memo.tex, output_file: memo/memo.pdf }
"""


@pytest.fixture(scope="module")
def version(tmp_path_factory: pytest.TempPathFactory) -> TemplateVersion:
    root = tmp_path_factory.mktemp("packs")
    vdir = root / "p" / "templates" / "t" / "versions" / "1.0.0"
    vdir.mkdir(parents=True)
    (root / "p" / "pack.yaml").write_text("id: p\n", encoding="utf-8")
    (root / "p" / "templates" / "t" / "template.yaml").write_text("id: t\n", encoding="utf-8")
    (vdir / "version.yaml").write_text(_VERSION, encoding="utf-8")
    loaded = YamlTemplateRepository(root).get_version("p", "t", "1.0.0")
    assert loaded is not None
    return loaded


@dataclass
class _Ws:
    id: UUID


class FakeWorkspaces:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def ready(self, actor: Actor, workspace_id: UUID) -> tuple[_Ws, Path]:
        return _Ws(workspace_id), self.root

    async def get(self, actor: Actor, workspace_id: UUID) -> _Ws:
        return _Ws(workspace_id)


@dataclass
class FakeRenderer:
    version: TemplateVersion
    files: dict[str, str] = field(
        default_factory=lambda: {"files/report/report.tex": "r1", "files/memo/memo.tex": "m1"}
    )
    fail: str | None = None
    describes: int = 0
    gate: asyncio.Event | None = None

    async def inputs(self, root: Path, ref: VersionRef) -> PreviewInputs:
        return PreviewInputs(files=dict(self.files), extra=(), tree=str(sorted(self.files.items())))

    async def describe(self, root: Path, ref: VersionRef) -> VersionDescription:
        self.describes += 1
        return VersionDescription("p", "t", self.version)

    async def materialize(
        self, root: Path, ref: VersionRef, request: MaterializeRequest, dest: Path
    ) -> MaterializedDoc:
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise PreviewRenderError(self.fail)
        source = f"{request.def_id}/{request.def_id}.tex"
        (dest / request.def_id).mkdir(parents=True, exist_ok=True)
        (dest / source).write_text("tex", encoding="utf-8")
        return MaterializedDoc(request.def_id, request.def_id, source, "", "xelatex", True, 1, ("warn",))


class FakeDispatcher:
    def __init__(self) -> None:
        self.submitted: dict[UUID, tuple[JobSpec, IJobHooks]] = {}
        self.cancelled: list[UUID] = []
        self.refuse: Exception | None = None

    async def preflight(self, spec: JobSpec) -> None:
        if self.refuse is not None:
            raise self.refuse

    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None:
        self.submitted[spec.id] = (spec, hooks)

    async def cancel(self, job_id: UUID) -> bool:
        self.cancelled.append(job_id)
        spec, hooks = self.submitted[job_id]
        await hooks.on_finished(spec, JobResult(status=JobStatus.cancelled), "[cancelled]")
        return True

    def is_active(self, job_id: UUID) -> bool:
        return job_id in self.submitted

    async def succeed(self, job_id: UUID, *, pdf: bool = True) -> None:
        spec, hooks = self.submitted[job_id]
        assert await hooks.on_started(spec)
        if pdf and spec.local_root is not None:
            (spec.local_root / spec.payload.source_file.replace(".tex", ".pdf")).write_bytes(b"%PDF-1.4")  # type: ignore[attr-defined]
        data = CompileResult(build_ok=True, pages=3, finished_at=datetime.now(UTC))
        await hooks.on_finished(spec, JobResult(status=JobStatus.succeeded, data=data), "latexmk ok")


@dataclass
class Rig:
    service: PackPreviewService
    renderer: FakeRenderer
    dispatcher: FakeDispatcher
    store: FsPreviewStore

    async def start(self, *docs: str, **kwargs: Any) -> list[Any]:
        builds = await self.service.start(ACTOR, WS, "p", "t", "1.0.0", StartPreviewInput(documents=docs, **kwargs))
        await self.service.wait_launched()
        return [await self.service.get(ACTOR, WS, b.id) for b in builds]


def _rig(
    tmp_path: Path, version: TemplateVersion, *, max_concurrent: int = 2, store: FsPreviewStore | None = None
) -> Rig:
    renderer = FakeRenderer(version)
    dispatcher = FakeDispatcher()
    store = store or FsPreviewStore(tmp_path / "previews", max_cache_entries=10, max_age_s=3600)
    service = PackPreviewService(
        FakeWorkspaces(tmp_path / "packs"),  # type: ignore[arg-type]
        renderer,
        store,
        dispatcher,
        limits=PreviewLimits(max_concurrent=max_concurrent),
        today=lambda: date(2026, 11, 15),
    )
    return Rig(service, renderer, dispatcher, store)


async def test__start__success_goes_to_cache_and_repeat_is_a_cache_hit(
    tmp_path: Path, version: TemplateVersion
) -> None:
    rig = _rig(tmp_path, version)

    [build] = await rig.start("report")
    await rig.dispatcher.succeed(build.id)
    done = await rig.service.get(ACTOR, WS, build.id)
    [again] = await rig.start("report")

    assert done.status is PreviewStatus.succeeded
    assert done.pages == 3
    assert (await rig.service.pdf(ACTOR, WS, build.id)).read_bytes() == b"%PDF-1.4"
    assert "[render] warn" in await rig.service.log(ACTOR, WS, build.id)
    assert again.cached is True
    assert again.status is PreviewStatus.succeeded
    assert len(rig.dispatcher.submitted) == 1
    assert rig.renderer.describes == 1  # модель версии разобрана один раз на одно содержимое
    assert not (tmp_path / "previews" / "work" / str(build.id)).exists()


async def test__start__same_key_while_running__returns_the_running_build(
    tmp_path: Path, version: TemplateVersion
) -> None:
    rig = _rig(tmp_path, version)

    [first] = await rig.start("report")
    [second] = await rig.start("report")

    assert second.id == first.id
    assert len(rig.dispatcher.submitted) == 1


async def test__start__same_slot_new_content__cancels_the_previous_build(
    tmp_path: Path, version: TemplateVersion
) -> None:
    rig = _rig(tmp_path, version)
    [first] = await rig.start("report")
    rig.renderer.files["files/report/report.tex"] = "r2"

    [second] = await rig.start("report")

    assert second.id != first.id
    assert rig.dispatcher.cancelled == [first.id]
    assert (await rig.service.get(ACTOR, WS, first.id)).status is PreviewStatus.cancelled


async def test__start__over_the_concurrent_limit__preview_quota(tmp_path: Path, version: TemplateVersion) -> None:
    rig = _rig(tmp_path, version, max_concurrent=1)
    await rig.start("report")

    with pytest.raises(PackStudioError) as caught:
        await rig.start("memo")

    assert caught.value.code.value == "preview_quota"
    assert caught.value.ctx == {"limit": 1}


async def test__start__render_failure_and_setup_refusal__failed_builds(
    tmp_path: Path, version: TemplateVersion
) -> None:
    rig = _rig(tmp_path, version)
    rig.renderer.fail = "SecurityError: access to attribute"
    [rendered] = await rig.start("report")
    rig.renderer.fail = None
    rig.dispatcher.refuse = ImageMissingError("texlive/texlive:latest")
    [refused] = await rig.start("memo")

    assert rendered.status is PreviewStatus.failed
    assert rendered.error is not None
    assert rendered.error.code == "render_failed"
    assert "SecurityError" in await rig.service.log(ACTOR, WS, rendered.id)
    assert refused.status is PreviewStatus.failed
    assert refused.error is not None
    assert refused.error.code == "image_missing"
    assert rig.dispatcher.submitted == {}


async def test__finish__no_pdf__pdf_missing(tmp_path: Path, version: TemplateVersion) -> None:
    rig = _rig(tmp_path, version)
    [build] = await rig.start("report")

    await rig.dispatcher.succeed(build.id, pdf=False)

    done = await rig.service.get(ACTOR, WS, build.id)
    assert done.status is PreviewStatus.failed
    assert done.error is not None
    assert done.error.code == "pdf_missing"
    with pytest.raises(PackStudioError) as caught:
        await rig.service.pdf(ACTOR, WS, build.id)
    assert caught.value.code.value == "preview_not_ready"


async def test__get__build_of_a_dead_process__interrupted(tmp_path: Path, version: TemplateVersion) -> None:
    rig = _rig(tmp_path, version)
    [build] = await rig.start("report")
    restarted = _rig(tmp_path, version, store=rig.store)

    seen = await restarted.service.get(ACTOR, WS, build.id)

    assert seen.status is PreviewStatus.failed
    assert seen.error is not None
    assert seen.error.code == "interrupted"


async def test__get__other_workspace_or_owner__not_found(tmp_path: Path, version: TemplateVersion) -> None:
    rig = _rig(tmp_path, version)
    [build] = await rig.start("report")

    with pytest.raises(PackStudioError) as other_ws:
        await rig.service.get(ACTOR, uuid4(), build.id)
    with pytest.raises(PackStudioError) as other_owner:
        await rig.service.get(Actor.user("someone-else", "Кто-то"), WS, build.id)

    assert other_ws.value.code.value == "preview_not_found"
    assert other_owner.value.code.value == "preview_not_found"


async def test__cancel__running_build__cancelled(tmp_path: Path, version: TemplateVersion) -> None:
    rig = _rig(tmp_path, version)
    [build] = await rig.start("report")

    await rig.service.cancel(ACTOR, WS, build.id)

    assert (await rig.service.get(ACTOR, WS, build.id)).status is PreviewStatus.cancelled


async def test__cancel__while_rendering__nothing_is_submitted(tmp_path: Path, version: TemplateVersion) -> None:
    rig = _rig(tmp_path, version)
    rig.renderer.gate = asyncio.Event()
    [build] = await rig.service.start(ACTOR, WS, "p", "t", "1.0.0", StartPreviewInput(documents=["report"]))
    await asyncio.sleep(0)

    cancelled = await rig.service.cancel(ACTOR, WS, build.id)
    rig.renderer.gate.set()
    await rig.service.wait_launched()

    assert cancelled.status is PreviewStatus.cancelled
    assert rig.dispatcher.submitted == {}
    assert not (tmp_path / "previews" / "work" / str(build.id)).exists()
