"""Заготовка «Минимальный» Студии шаблонов собирается на настоящем TeX Live (template-studio.md, раздел 8).

Новый пак тем же кодом, что у окна «Новый пак», синтетический проект набора «Обычный» тем же кодом, что у
предпросмотра, сборка XeLaTeX профилем раннера. Нужны docker и образ TeX в HSE_TEST_TEX_IMAGE:

    HSE_TEST_TEX_IMAGE=texlive/texlive:TL2024-historic uv run pytest tests/integration/tex -m tex --no-cov
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from hse_doc_studio.core.pack_studio.preview import (
    MaterializeRequest,
    auto_examples,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.core.pack_studio.scaffold import NewPack, NewTemplate
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE
from hse_doc_studio.infra.pack_studio.preview_worker import (
    StageLimits,
    VersionDirs,
    describe_version,
    materialize_preview,
)
from hse_doc_studio.infra.pack_studio.scaffold import PackScaffolder
from pypdf import PdfReader

pytestmark = [
    pytest.mark.tex,
    pytest.mark.timeout(900),
    pytest.mark.skipif(not os.environ.get("HSE_TEST_TEX_IMAGE"), reason="нет образа TeX (HSE_TEST_TEX_IMAGE)"),
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="профиль раннера берёт uid процесса (POSIX)"),
]

_CACHE_VOLUME = "hds-test-tex-cache"
_LIMITS = StageLimits(max_bytes=10 * 1024 * 1024, max_files=1000)
_TODAY = date(2026, 11, 15)


async def test__minimal_scaffold__builds_the_report(tmp_path: Path) -> None:
    packs = tmp_path / "packs"
    packs.mkdir()
    pack = NewPack(
        id="new-pack",
        name={"ru": "Новый пак", "en": "New pack"},
        template=NewTemplate(id="report", name={"ru": "Отчёт", "en": "Report"}),
    )
    PackScaffolder(max_files=1000, max_bytes=10 * 1024 * 1024).create_pack(
        packs, pack, version="2026.1", today=_TODAY, source=None
    )
    dirs = VersionDirs(str(packs), "new-pack", "report", "2026.1")
    desc = describe_version(dirs, str(tmp_path / "describe"), _LIMITS)
    example = next(e for e in auto_examples(desc.version) if e.id == "auto:normal")
    project = synthetic_project(desc.version, example, resolve_combination(switches_for(desc.version), {}), _TODAY)
    request = MaterializeRequest(desc.pack_id, desc.template_id, desc.version.version, "report", project, uuid.uuid4())
    work = tmp_path / "work"
    doc = materialize_preview(dirs, str(tmp_path / "stage"), _LIMITS, request, str(work))
    assert doc.warnings == ()

    executor = DockerCompileExecutor(
        HostPathResolver(),
        image=os.environ["HSE_TEST_TEX_IMAGE"],
        cache_volume_name=_CACHE_VOLUME,
        limits=ExecutorLimits(user=f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else None),
    )
    lines = await executor.run(
        project_folder=work,
        source_file=doc.source_file,
        engine="xelatex",
        max_iterations=doc.default_passes + 2,
        doc_id="report",
        compile_id=uuid.uuid4(),
    )
    log = [line async for line in lines]

    assert log[-1] == SENTINEL_DONE, "\n".join(log[-60:])
    reader = PdfReader(BytesIO((work / "report" / "report.pdf").read_bytes()))
    title = reader.pages[0].extract_text()
    assert "ОТЧЁТ" in title
    assert project.name.split()[0] in title
    assert "СОДЕРЖАНИЕ" in reader.pages[1].extract_text()
