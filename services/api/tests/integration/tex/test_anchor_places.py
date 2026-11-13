"""Места подписей на якорях на настоящем TeX Live (docs/design/signing-route.md, 15.17.8 и 15.17.9).

Синтетический пак: эталон макросов `infra/compile/tex/anchors.tex` в `common/anchors.tex`, документ с обёрткой
`\\hseSignField[<слот>]` и строкой даты, места в `version.yaml` только на якорях. Линтер пака его принимает; сборка
XeLaTeX в разных вёрстках (язык, строка консультанта) даёт разные места без правки пака, ручное место не двигается,
а шаблон без якорей оставляет места как есть. Нужны docker и образ TeX в HSE_TEST_TEX_IMAGE:

    HSE_TEST_TEX_IMAGE=texlive/texlive:TL2024-historic uv run pytest tests/integration/tex -m tex --no-cov
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import hse_doc_studio.infra.compile as compile_pkg
import pytest
import yaml
from hse_doc_studio.core.catalog import SignaturesConfig, SignatureSlotDef, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, pack_placement
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.template.pack_lint import lint_version_dir
from hse_doc_studio.infra.template.yaml_template_repository import _parse_signature_slot
from hse_doc_studio.use_cases.signatures.anchor_places import BuildPlaces
from hse_doc_studio.use_cases.signatures.source_anchors import doc_anchors_sync

from tests.factories import make_document, make_project, make_template_version

pytestmark = [
    pytest.mark.tex,
    pytest.mark.timeout(900),
    pytest.mark.skipif(not os.environ.get("HSE_TEST_TEX_IMAGE"), reason="нет образа TeX (HSE_TEST_TEX_IMAGE)"),
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="профиль раннера берёт uid процесса (POSIX)"),
]

_CACHE_VOLUME = "hds-test-tex-cache"
MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"
VERSION_ID = "2026.9.1"

# Шапка на русском длиннее на 30 мм (как у «Заявления»: английская короче); строка консультанта печатается, только
# если он указан, и сдвигает строку академрука. Строки подписей прижаты к правому полю обёрткой `\hseSignField`.
_MAIN = r"""\documentclass[12pt]{article}
\usepackage[a4paper,left=30mm,right=15mm,top=20mm,bottom=20mm]{geometry}
\setlength{\parindent}{0pt}
\pagestyle{empty}
\input{../common/meta}
\input{../common/anchors}
\newcommand\hseSignField[2][]{\hseSignAnchor[#2]{#1}\rule{#2}{0.4pt}}
\begin{document}
Topic application\par
\ifhseLangEn\else\vspace{30mm}\fi
\vspace{40mm}
\hfill Supervisor \hseSignField[supervisor]{25.5mm}\par
\vspace{15mm}
\hfill Student \hseSignField[author]{34mm}\par
\vspace{10mm}
\ifhseConsultant\hfill Consultant \hseSignField[co_supervisor]{25.5mm}\par\vspace{10mm}\fi
\hfill Academic supervisor \hseSignField[academic_supervisor]{25.5mm}\par
\vspace{10mm}
Date: \hseDateAnchor[8mm]{supervisor}{day}\rule{8mm}{0.4pt}
\end{document}
"""


def _meta(*, en: bool = False, consultant: bool = False) -> str:
    flags = [r"\newif\ifhseLangEn", r"\newif\ifhseConsultant"]
    flags += [r"\hseLangEntrue"] if en else []
    flags += [r"\hseConsultanttrue"] if consultant else []
    return "\n".join(flags) + "\n"


_MANIFEST: dict[str, Any] = {
    "id": VERSION_ID,
    "langs": ["ru", "en"],
    "documents": [{"id": "tz", "source_file": "tz/main.tex", "output_file": "tz/main.pdf"}],
    "signatures": {
        "anchor_macros": ["hseSignField"],
        "slots": [
            {
                "id": "supervisor",
                "applies_to": ["tz"],
                "placements": {"tz": {"anchor": "supervisor", "align": "right", "width_mm": 28}},
                "default_dates": {"tz": [{"anchor": "supervisor.day"}]},
            },
            {
                "id": "author",
                "applies_to": ["tz"],
                "placements": {"tz": {"anchor": "author", "align": "right", "dy_mm": -11, "width_mm": 30}},
            },
            {
                "id": "co_supervisor",
                "applies_to": ["tz"],
                "placements": {"tz": {"anchor": "co_supervisor", "align": "right", "width_mm": 28}},
            },
            {
                "id": "academic_supervisor",
                "applies_to": ["tz"],
                "placements": {"tz": {"anchor": "academic_supervisor", "align": "right", "width_mm": 28}},
            },
        ],
    },
}


def _pack(root: Path) -> Path:
    """Версия синтетического пака: `version.yaml` и файлы с эталоном макросов в `common/anchors.tex`."""
    files = root / "files"
    (files / "tz").mkdir(parents=True)
    (files / "common").mkdir()
    shutil.copyfile(MACROS, files / "common" / "anchors.tex")
    (files / "common" / "meta.tex").write_text(_meta(), encoding="utf-8")
    (files / "tz" / "main.tex").write_text(_MAIN, encoding="utf-8")
    (root / "version.yaml").write_text(yaml.safe_dump(_MANIFEST), encoding="utf-8")
    return root


def _version() -> TemplateVersion:
    slots = tuple(_parse_signature_slot(slot) for slot in _MANIFEST["signatures"]["slots"])
    return replace(make_template_version(version=VERSION_ID), signatures_config=SignaturesConfig(slots=slots))


class _Sources:
    def resolve_instance_source(self, project: Project, doc: Any, version: Any) -> tuple[str, str]:
        return "tz/main.tex", "tz/main.pdf"

    def resolve_signing_output(self, project: Project, doc: Any, version: Any) -> str:
        return "tz/main.pdf"


class _Repos:
    def __init__(self, project: Project, version: TemplateVersion) -> None:
        self.project = project
        self.version = version

    def get(self, folder: Path) -> Project:
        return self.project

    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion:
        return self.version


def _executor() -> DockerCompileExecutor:
    limits = ExecutorLimits(user=f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else None)
    return DockerCompileExecutor(
        HostPathResolver(), image=os.environ["HSE_TEST_TEX_IMAGE"], cache_volume_name=_CACHE_VOLUME, limits=limits
    )


class _Stand:
    """Проект из файлов пака, его сборка XeLaTeX и пересчёт мест после неё."""

    def __init__(self, root: Path, pack: Path) -> None:
        self.folder = root
        shutil.copytree(pack / "files", root)
        self.version = _version()
        self.project = make_project(folder=root, documents=[make_document("tz")])
        repos = _Repos(self.project, self.version)
        self.repo = JsonSignatureRepository()
        self.places = BuildPlaces(repos, repos, self.repo, _Sources())  # type: ignore[arg-type]

    async def build(self, **layout: bool) -> None:
        (self.folder / "common" / "meta.tex").write_text(_meta(**layout), encoding="utf-8")
        lines = await _executor().run(
            project_folder=self.folder,
            source_file="tz/main.tex",
            engine="xelatex",
            max_iterations=5,
            doc_id="tz",
            compile_id=uuid.uuid4(),
        )
        log = [line async for line in lines]
        assert log[-1] == SENTINEL_DONE, "\n".join(log[-60:])

    def anchors(self) -> SourceAnchors:
        state = self.repo.get_state(self.folder)
        return doc_anchors_sync(_Sources(), self.project, self.version, state, self.project.documents[0])  # type: ignore[arg-type]

    def slot(self, slot_id: str) -> SignatureSlotDef:
        return next(s for s in self.version.signatures_config.slots if s.id == slot_id)

    def place(self, *slot_ids: str) -> None:
        """Места из шаблона по якорям текущей сборки, как их ставит черновик маршрута."""
        src = self.anchors()
        placements: dict[str, SignaturePlacement] = {}
        for slot_id in slot_ids:
            placed = pack_placement(self.slot(slot_id), "tz", None, VERSION_ID, src)
            assert placed is not None, slot_id
            placements[slot_id] = replace(placed, enabled=True)
        self.repo.save_state(self.folder, SignaturesState(slots={}, placements={"tz": placements}))

    def box(self, slot_id: str) -> SignaturePlacement:
        return self.repo.get_state(self.folder).placements["tz"][slot_id]

    async def after_build(self) -> int:
        return await self.places.after_build(self.project.id, self.folder, "tz")


def test__lint__synthetic_pack_on_anchors_passes(tmp_path: Path) -> None:
    report = lint_version_dir(_pack(tmp_path / "pack"))

    assert report.errors == []
    assert [w for w in report.warnings if "якор" in w] == []


async def test__xelatex__layouts_move_places_without_pack_edits(tmp_path: Path) -> None:
    stand = _Stand(tmp_path / "proj", _pack(tmp_path / "pack"))
    await stand.build()
    stand.place("supervisor", "author", "academic_supervisor")
    ru = {slot_id: stand.box(slot_id) for slot_id in ("supervisor", "author", "academic_supervisor")}
    src = stand.anchors()
    assert src.known
    assert src.line("co_supervisor") is None  # строки консультанта нет: он не указан
    line = src.line("supervisor")
    assert line is not None
    # Рамка прижата к правому концу линии (правое поле 195 мм), верх на 10 мм выше базовой линии.
    assert ru["supervisor"].x_mm + ru["supervisor"].width_mm == pytest.approx(195.0, abs=0.1)
    assert ru["supervisor"].y_mm == pytest.approx(line.y_mm - 10.0, abs=0.05)
    assert [mark.format for mark in ru["supervisor"].dates] == ["day"]

    await stand.build(en=True)
    moved_en = await stand.after_build()

    # Английская шапка короче на 30 мм: все места выше на 30 мм, по горизонтали на месте.
    assert moved_en == 3
    for slot_id, before in ru.items():
        after = stand.box(slot_id)
        assert after.y_mm == pytest.approx(before.y_mm - 30.0, abs=0.2), slot_id
        assert (after.x_mm, after.width_mm, after.enabled) == (before.x_mm, before.width_mm, True)
    en_day = stand.box("supervisor").dates[0].y_mm
    assert en_day == pytest.approx(ru["supervisor"].dates[0].y_mm - 30.0, abs=0.2)

    # Автор передвинул свою рамку руками; строка консультанта сдвигает академрука, научрук и автор на месте.
    manual = replace(stand.box("author"), x_mm=120.0)
    state = stand.repo.get_state(stand.folder)
    stand.repo.save_state(stand.folder, replace(state, placements={"tz": {**state.placements["tz"], "author": manual}}))
    academic_en = stand.box("academic_supervisor").y_mm
    supervisor_en = stand.box("supervisor").y_mm

    await stand.build(en=True, consultant=True)
    moved_consultant = await stand.after_build()

    # Академрук и строка даты научрука (она ниже строки консультанта) сдвинулись; рамка научрука на месте.
    assert moved_consultant == 2
    assert stand.box("academic_supervisor").y_mm > academic_en + 10.0
    assert stand.box("supervisor").y_mm == supervisor_en
    assert stand.box("supervisor").dates[0].y_mm > en_day + 10.0
    assert stand.box("author") == manual
    assert stand.anchors().line("co_supervisor") is not None


async def test__xelatex__template_without_anchors__places_stay(tmp_path: Path) -> None:
    stand = _Stand(tmp_path / "proj", _pack(tmp_path / "pack"))
    await stand.build()
    stand.place("supervisor")
    before = stand.box("supervisor")
    # Шаблон перестал подключать макросы (или собрал раннер прежней версии): якоря неизвестны.
    main = stand.folder / "tz" / "main.tex"
    main.write_text(
        main.read_text(encoding="utf-8").replace("\\input{../common/anchors}\n", "\\input{../common/off}\n")
    )
    (stand.folder / "common" / "off.tex").write_text(
        "\\newcommand\\hseSignAnchor[2][]{}\\newcommand\\hseDateAnchor[3][]{}\n", encoding="utf-8"
    )

    await stand.build(en=True)

    assert not stand.anchors().known
    assert await stand.after_build() == 0
    assert stand.box("supervisor") == before
