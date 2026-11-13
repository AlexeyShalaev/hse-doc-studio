"""Якоря мест подписей на настоящем TeX Live (docs/design/signing-route.md, 15.17.3 и 15.17.5).

Макросы `hse_doc_studio/infra/compile/tex/anchors.tex` (эталон `common/anchors.tex` пака) в XeLaTeX: позиции линий,
перевод в `anchors.json` при публикации, PDF байт в байт как без якорей, пересборка без правок и шаблон, переставший
подключать макросы. Нужны docker и образ TeX в HSE_TEST_TEX_IMAGE, как у `test_reproducible_build.py`:

    HSE_TEST_TEX_IMAGE=texlive/texlive:TL2024-historic uv run pytest tests/integration/tex -m tex --no-cov
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import hse_doc_studio.infra.compile as compile_pkg
import pytest
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE

pytestmark = [
    pytest.mark.tex,
    pytest.mark.timeout(900),
    pytest.mark.skipif(not os.environ.get("HSE_TEST_TEX_IMAGE"), reason="нет образа TeX (HSE_TEST_TEX_IMAGE)"),
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="профиль раннера берёт uid процесса (POSIX)"),
]

_CACHE_VOLUME = "hds-test-tex-cache"
MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"

# Поля 30 мм слева и 20 мм сверху, без абзацного отступа: первая строка страницы стоит на базовой
# 20 мм + \topskip (12pt = 4,2 мм), левый край текста на 30 мм. Якорь в `tabularx` (пробные проходы таблицы
# позиций не пишут), дата на второй странице, якорь с именем через подчёркивание.
_SOURCE = r"""\documentclass[12pt]{article}
\usepackage[a4paper,left=30mm,right=15mm,top=20mm,bottom=20mm]{geometry}
\usepackage{tabularx}
\setlength{\parindent}{0pt}
\pagestyle{empty}
%ANCHORS%\input{../common/anchors}
\begin{document}
%ANCHORS%\hseSignAnchor[40mm]{supervisor}%
\rule{40mm}{0.4pt}

\vspace{20mm}
\begin{tabularx}{\textwidth}{@{}X@{}}
%ANCHORS%\hseSignAnchor[\linewidth]{academic_supervisor}%
\rule{\linewidth}{0.4pt}\\
\end{tabularx}

\newpage
Date: \hfill
%ANCHORS%\hseDateAnchor[10mm]{supervisor}{day}%
\rule{10mm}{0.4pt}
\end{document}
"""


def _source(*, anchors: bool) -> str:
    return _SOURCE.replace("%ANCHORS%", "" if anchors else "%")


def _project(root: Path, *, anchors: bool = True) -> Path:
    (root / "tz").mkdir(parents=True)
    (root / "common").mkdir()
    shutil.copyfile(MACROS, root / "common" / "anchors.tex")
    (root / "tz" / "main.tex").write_text(_source(anchors=anchors), encoding="utf-8")
    return root


def _executor() -> DockerCompileExecutor:
    # Профиль общего и личного раннера и пода kubernetes: не root, формат движка собирается заново.
    limits = ExecutorLimits(user=f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else None)
    return DockerCompileExecutor(
        HostPathResolver(), image=os.environ["HSE_TEST_TEX_IMAGE"], cache_volume_name=_CACHE_VOLUME, limits=limits
    )


async def _build(project: Path) -> list[str]:
    lines = await _executor().run(
        project_folder=project,
        source_file="tz/main.tex",
        engine="xelatex",
        max_iterations=5,
        doc_id="tz",
        compile_id=uuid.uuid4(),
    )
    log = [line async for line in lines]
    assert log[-1] == SENTINEL_DONE, "\n".join(log[-60:])
    return log


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchors(project: Path) -> dict[str, object] | None:
    path = project / "tz" / ".build" / "tz" / "main.anchors.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None  # type: ignore[no-any-return]


def _by_id(anchors: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["id"]: item for item in anchors["anchors"]}  # type: ignore[attr-defined,index]


@dataclass(frozen=True)
class _Built:
    project: Path
    pdf_sha: str
    anchors: dict[str, object]


@pytest.fixture(scope="module")
async def built(tmp_path_factory: pytest.TempPathFactory) -> _Built:
    project = _project(tmp_path_factory.mktemp("anchors"))
    await _build(project)
    anchors = _anchors(project)
    assert anchors is not None
    return _Built(project, _sha(project / "tz" / "main.pdf"), anchors)


def test__xelatex__positions_file_written_in_the_build_dir(built: _Built) -> None:
    raw = (built.project / "tz" / ".build" / "tz" / "main.hsepos").read_text(encoding="ascii").splitlines()

    assert re.fullmatch(r"hsepos 1 \d+ \d+", raw[0])
    assert [line.split()[:3] for line in raw[1:]] == [
        ["sign", "supervisor", "-"],
        ["sign", "academic_supervisor", "-"],
        ["date", "supervisor", "day"],
    ]


def test__xelatex__anchors_bound_to_the_published_pdf(built: _Built) -> None:
    assert built.anchors["format"] == 1
    assert built.anchors["pdf_sha256"] == built.pdf_sha
    assert built.anchors["problems"] == []
    assert built.anchors["duplicates"] == []


def test__xelatex__line_positions_from_the_layout(built: _Built) -> None:
    anchors = _by_id(built.anchors)

    assert anchors["supervisor"] == {
        "id": "supervisor",
        "kind": "sign",
        "page": 1,
        "x_mm": 30.0,
        "y_mm": 24.2,
        "width_mm": 40.0,
    }
    # Таблица шириной в текст: линия от левого поля до правого (210 - 30 - 15 = 165 мм), ниже первой строки.
    table = anchors["academic_supervisor"]
    assert (table["page"], table["x_mm"], table["width_mm"]) == (1, 30.0, 165.0)
    assert float(table["y_mm"]) > 44.0  # type: ignore[arg-type]
    # Дата прижата к правому полю на второй странице: правый край линии на 195 мм.
    day = anchors["supervisor.day"]
    assert (day["kind"], day["page"], day["width_mm"]) == ("date", 2, 10.0)
    assert float(day["x_mm"]) + float(day["width_mm"]) == pytest.approx(195.0, abs=0.1)  # type: ignore[arg-type]


async def test__xelatex__pdf_with_and_without_anchors_byte_identical(built: _Built, tmp_path: Path) -> None:
    plain = _project(tmp_path / "plain", anchors=False)

    await _build(plain)

    assert _sha(plain / "tz" / "main.pdf") == built.pdf_sha
    assert _anchors(plain) is None


async def test__xelatex__rebuild_without_changes__same_anchors(built: _Built) -> None:
    # latexmk перезапускает только xdvipdfmx: файл позиций прошлого прохода TeX и есть позиции нового PDF.
    log = await _build(built.project)

    assert _sha(built.project / "tz" / "main.pdf") == built.pdf_sha
    assert _anchors(built.project) == built.anchors
    assert any("xdvipdfmx" in line for line in log)


async def test__xelatex__template_stops_loading_anchors__anchors_become_unknown(tmp_path: Path) -> None:
    project = _project(tmp_path / "stale")
    await _build(project)
    assert _anchors(project) is not None

    (project / "tz" / "main.tex").write_text(_source(anchors=False), encoding="utf-8")
    await _build(project)

    # Файл позиций остался от прошлой сборки, но последний проход TeX его не писал.
    assert (project / "tz" / ".build" / "tz" / "main.hsepos").exists()
    assert _anchors(project) is None
