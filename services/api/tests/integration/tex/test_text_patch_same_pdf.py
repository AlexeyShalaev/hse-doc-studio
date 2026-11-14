"""Patch-версии с исправленными текстами `{ ru, en }` дают тот же PDF, что и предыдущие, настоящий TeX Live.

`hse-cs-sse/coursework` 2026.1.6, `hse-cs-se/coursework` и `vkr` 2026.1.2, `hse-cs-se/pp` 2026.1.1 отличаются от
предыдущих версий только кавычками у подписей полей, названий проверок и описания точки (запятая без кавычек резала
строку, `flow_text_lint`). Подписи в документ не печатаются: каждый документ и каждый LaTeX-вариант обеих версий
собирается с одними данными проекта, и PDF совпадают байт в байт.

Нужны docker и образ TeX в HSE_TEST_TEX_IMAGE:

    HSE_TEST_TEX_IMAGE=texlive/texlive:TL2024-historic uv run pytest tests/integration/tex -m tex --no-cov
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EngineType, Lang, PersonRole, ProjectKind
from hse_doc_studio.core.value_objects import Author, Person, ProjectLock
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_base,
    regenerate_dynamic_includes,
)
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

from tests.factories import make_document, make_project

pytestmark = [
    pytest.mark.tex,
    pytest.mark.timeout(1800),
    pytest.mark.skipif(not os.environ.get("HSE_TEST_TEX_IMAGE"), reason="нет образа TeX (HSE_TEST_TEX_IMAGE)"),
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="профиль раннера берёт uid процесса (POSIX)"),
]

_CACHE_VOLUME = "hds-test-tex-cache"
PACKS = Path(__file__).resolve().parents[5] / "packs"
# Сборок сразу: раннер с несколькими задачами, но без перегрузки машины разработчика.
_PARALLEL = 4


@dataclass(frozen=True)
class _Case:
    pack: str
    template: str
    released: str
    patched: str
    lang: str
    kind: ProjectKind

    @property
    def key(self) -> str:
        return f"{self.pack}-{self.template}-{self.patched}-{self.lang}-{self.kind.value}"


_CASES = [
    _Case("hse-cs-sse", "coursework", "2026.1.5", "2026.1.6", "ru", ProjectKind.project),
    _Case("hse-cs-sse", "coursework", "2026.1.5", "2026.1.6", "en", ProjectKind.project),
    _Case("hse-cs-se", "coursework", "2026.1.1", "2026.1.2", "ru", ProjectKind.project),
    _Case("hse-cs-se", "coursework", "2026.1.1", "2026.1.2", "ru", ProjectKind.research),
    _Case("hse-cs-se", "vkr", "2026.1.1", "2026.1.2", "ru", ProjectKind.project),
    _Case("hse-cs-se", "vkr", "2026.1.1", "2026.1.2", "ru", ProjectKind.research),
    _Case("hse-cs-se", "pp", "2026.1", "2026.1.1", "en", ProjectKind.research),
]


@dataclass(frozen=True)
class _Target:
    """Что собрать: документ или его LaTeX-вариант."""

    name: str
    source: str
    output: str


def _fits(case: _Case, langs: tuple[str, ...]) -> bool:
    return not langs or case.lang in langs


def _targets(version: TemplateVersion, case: _Case) -> list[_Target]:
    out: list[_Target] = []
    docs = [d for d in version.documents if case.kind.value in d.supported_kinds and "solo" in d.supported_staffing]
    for doc in (d for d in docs if _fits(case, d.supported_langs)):
        if doc.source_file and doc.output_file and doc.source_file.endswith(".tex"):
            out.append(_Target(doc.id, doc.source_file, doc.output_file))
        out.extend(
            _Target(f"{doc.id}/{variant.id}", variant.source_file, variant.output_file)
            for variant in doc.variants
            if _fits(case, variant.supported_langs)
            and variant.engine is not None
            and variant.source_file.endswith(".tex")
        )
    return out


def _project(version: TemplateVersion, case: _Case, version_id: str, folder: Path) -> Project:
    base = make_project(
        folder=folder,
        name="Контур согласования действий агента",
        documents=[make_document(d.id) for d in version.documents],
    )
    return replace(
        base,
        lock=ProjectLock(pack_id=case.pack, template_id=case.template, version=version_id, engine=EngineType.xelatex),
        kind=case.kind,
        lang=Lang(case.lang),
        authors=[Author(name="Иванов Иван Иванович", group="БПИ221")],
        supervisor=Person(name="Петров Пётр Петрович", role=PersonRole.university, title="доцент", degree="к.т.н."),
        meta={"name_en": "An approval gate for LLM agents", "form_year": "2026"},
    )


def _executor() -> DockerCompileExecutor:
    limits = ExecutorLimits(user=f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else None)
    return DockerCompileExecutor(
        HostPathResolver(), image=os.environ["HSE_TEST_TEX_IMAGE"], cache_volume_name=_CACHE_VOLUME, limits=limits
    )


async def _build(folder: Path, target: _Target, gate: asyncio.Semaphore) -> bytes:
    async with gate:
        lines = await _executor().run(
            project_folder=folder,
            source_file=target.source,
            engine="xelatex",
            max_iterations=5,
            doc_id=target.name.replace("/", "-"),
            compile_id=uuid.uuid4(),
        )
        log = [line async for line in lines]
    assert log[-1] == SENTINEL_DONE, f"{folder} {target}:\n" + "\n".join(log[-60:])
    return (folder / target.output).read_bytes()


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    repo = YamlTemplateRepository(PACKS)
    repo.load()
    return repo


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.key)
def test__text_patch__every_document_builds_the_same_pdf(
    repo: YamlTemplateRepository, tmp_path: Path, case: _Case
) -> None:
    versions: dict[str, tuple[Path, list[_Target]]] = {}
    for version_id in (case.released, case.patched):
        version = repo.get_version(case.pack, case.template, version_id)
        assert version is not None, version_id
        folder = tmp_path / version_id / "proj"
        folder.mkdir(parents=True)
        project = _project(version, case, version_id, folder)
        instantiate_base(project, version, repo, TemplateRenderer(), "", None)
        regenerate_dynamic_includes(project, version, repo)
        versions[version_id] = (folder, _targets(version, case))

    (old_folder, targets), (new_folder, new_targets) = versions[case.released], versions[case.patched]
    assert targets == new_targets
    assert targets

    async def build_all() -> list[tuple[bytes, bytes]]:
        gate = asyncio.Semaphore(_PARALLEL)
        old = asyncio.gather(*(_build(old_folder, t, gate) for t in targets))
        new = asyncio.gather(*(_build(new_folder, t, gate) for t in targets))
        return list(zip(*await asyncio.gather(old, new), strict=True))

    for target, (old_pdf, new_pdf) in zip(targets, asyncio.run(build_all()), strict=True):
        assert old_pdf == new_pdf, target
