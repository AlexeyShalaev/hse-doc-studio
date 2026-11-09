"""Воспроизводимая сборка на настоящем TeX Live: две сборки без изменений дают один sha.

Нужны docker и образ TeX в HSE_TEST_TEX_IMAGE; образ тест не скачивает. В CI это джоба `tex-reproducible`, вручную:

    docker pull texlive/texlive:TL2024-historic
    HSE_TEST_TEX_IMAGE=texlive/texlive:TL2024-historic uv run pytest tests/integration/tex -m tex --no-cov
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE
from pypdf import PdfReader

pytestmark = [
    pytest.mark.tex,
    pytest.mark.timeout(900),
    pytest.mark.skipif(not os.environ.get("HSE_TEST_TEX_IMAGE"), reason="нет образа TeX (HSE_TEST_TEX_IMAGE)"),
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="профиль раннера берёт uid процесса (POSIX)"),
]

# Свой том кэша: тест не трогает кэш Студии на машине разработчика.
_CACHE_VOLUME = "hds-test-tex-cache"

# Кириллица, жирный и курсив (подмножества шрифтов в PDF), оглавление и закладки (несколько проходов latexmk),
# год сборки в тексте.
_SOURCE = r"""\documentclass[12pt]{article}
\usepackage{fontspec}
\setmainfont{cmunrm.otf}[BoldFont=cmunbx.otf, ItalicFont=cmunti.otf]
\newfontfamily\cyrillicfont{cmunrm.otf}[BoldFont=cmunbx.otf, ItalicFont=cmunti.otf]
\usepackage{polyglossia}
\setdefaultlanguage{russian}
\usepackage{hyperref}
\hypersetup{pdftitle={Воспроизводимая сборка}}
\begin{document}
\tableofcontents
\section{Введение}
Текст \textbf{жирный} и \textit{курсив}, формула $E = mc^2$.
\section{Дата}
YEAR\the\year END
\end{document}
"""


@dataclass(frozen=True)
class _Built:
    project: Path
    pdf: bytes
    years: frozenset[int]


def _project(root: Path) -> Path:
    (root / "tz").mkdir(parents=True)
    (root / "tz" / "main.tex").write_text(_SOURCE, encoding="utf-8")
    return root


def _runner_limits() -> ExecutorLimits:
    """Профиль общего и личного раннера (как `RunnerConfig.executor_limits`) и пода kubernetes.

    Не root, корень только для чтения, без сети; формат движка собирается заново в /tmp на каждую сборку.
    """
    return ExecutorLimits(user=f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else None)


def _executor(limits: ExecutorLimits | None) -> DockerCompileExecutor:
    return DockerCompileExecutor(
        HostPathResolver(), image=os.environ["HSE_TEST_TEX_IMAGE"], cache_volume_name=_CACHE_VOLUME, limits=limits
    )


async def _run(executor: DockerCompileExecutor, project: Path) -> list[str]:
    lines = await executor.run(
        project_folder=project,
        source_file="tz/main.tex",
        engine="xelatex",
        max_iterations=5,
        doc_id="tz",
        compile_id=uuid.uuid4(),
    )
    return [line async for line in lines]


async def _build(executor: DockerCompileExecutor, project: Path) -> bytes:
    log = await _run(executor, project)
    assert log[-1] == SENTINEL_DONE, "\n".join(log[-60:])
    return (project / "tz" / "main.pdf").read_bytes()


def _sha(pdf: bytes) -> str:
    return hashlib.sha256(pdf).hexdigest()


@pytest.fixture(scope="module")
async def first(tmp_path_factory: pytest.TempPathFactory) -> _Built:
    before = datetime.now(UTC).year
    project = _project(tmp_path_factory.mktemp("first"))
    pdf = await _build(_executor(_runner_limits()), project)
    return _Built(project, pdf, frozenset({before, datetime.now(UTC).year}))


async def test__rebuild__unchanged_project__same_sha256(first: _Built) -> None:
    # Вторая сборка в той же папке: latexmk видит готовые .aux, а PDF перенесён к исходнику и собирается заново.
    second = await _build(_executor(_runner_limits()), first.project)

    assert _sha(second) == _sha(first.pdf)


async def test__build__other_workspace__same_sha256(first: _Built, tmp_path: Path) -> None:
    # Другой раннер или новая рабочая папка: всё с нуля, без .aux и без кэша latexmk.
    other = await _build(_executor(_runner_limits()), _project(tmp_path / "other"))

    assert _sha(other) == _sha(first.pdf)


async def test__build__embedded_root_profile__same_sha256_as_runner(first: _Built, tmp_path: Path) -> None:
    # Встроенный раннер локальной Студии: root, без изоляции, готовый формат образа.
    project = _project(tmp_path / "embedded")
    log = await _run(_executor(None), project)
    if log[-1] != SENTINEL_DONE and any("I can't find the format file" in line for line in log):
        # Так у образов без готового формата xelatex (TL2024-historic): root собирает формат при сборке и падает.
        pytest.skip("в образе нет готового формата xelatex, профиль root на нём не собирает")
    assert log[-1] == SENTINEL_DONE, "\n".join(log[-60:])

    assert _sha((project / "tz" / "main.pdf").read_bytes()) == _sha(first.pdf)


def test__build__fixed_pdf_date_and_real_year_in_text(first: _Built, tmp_path: Path) -> None:
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(first.pdf)
    reader = PdfReader(pdf)
    info = reader.metadata
    text = "".join(page.extract_text() for page in reader.pages)

    assert info is not None
    assert str(info["/CreationDate"]).startswith("D:19800101000000")
    assert any(f"YEAR{year}" in text for year in first.years), text
