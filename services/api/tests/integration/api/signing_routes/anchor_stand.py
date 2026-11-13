"""Синтетический пак с местами на якорях шаблона для серверных тестов (docs/design/signing-route.md, 15.17).

Копия паков репозитория и в ней тестовая `hse-cs-sse/coursework` 2026.1.91: файлы выпущенной 2026.1.4, эталон
макросов `common/anchors.tex` и пресет 15.10, где места заданы не миллиметрами, а якорями (`anchor`, `align`, `dy_mm`,
у автора запасное место в мм). Сборку заменяет PDF на месте результата и `anchors.json` его сборки в `.build`, как их
оставляет публикация сборки; линии взяты из замеров 2026.1.4 (15.15).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import hse_doc_studio.infra.compile as compile_pkg
import pytest
import yaml
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors, encode_anchors
from hse_doc_studio.infra.template.releases import freeze

from tests.integration.api.signing_routes.preset_stand import _SIGNING_SLOTS, RELEASED_VERSION, REPO_PACKS

if TYPE_CHECKING:
    # Стенд тянет модели сервера: без extra server модуль собирается, а импорт только для типов.
    from tests.integration.api.signing_routes.stand import Project

ANCHOR_VERSION = "2026.1.91"
MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"

_ANCHOR_SLOTS: dict[str, dict[str, Any]] = {
    "supervisor": {
        "placements": {
            "topic_application": {"anchor": "supervisor", "align": "right", "width_mm": 28},
            "project_proposal": {"anchor": "supervisor", "align": "left", "dy_mm": -14, "width_mm": 40},
        },
        "default_dates": {
            "project_proposal": [
                {"anchor": "supervisor.day"},
                {"anchor": "supervisor.month_word"},
                {"anchor": "supervisor.month_number"},  # английская строка «__.__.2026»
            ]
        },
    },
    # Запасное место в мм: им место встаёт, пока якоря сборки неизвестны.
    "author": {
        "placements": {
            "topic_application": {
                "anchor": "author",
                "align": "right",
                "dy_mm": -11,
                "width_mm": 30,
                "page": 1,
                "x_mm": 165,
                "y_mm": 201,
            }
        }
    },
    "co_supervisor": {
        "placements": {"topic_application": {"anchor": "co_supervisor", "align": "right", "width_mm": 28}}
    },
    "academic_supervisor": {
        "placements": {"topic_application": {"anchor": "academic_supervisor", "align": "right", "width_mm": 28}}
    },
}


def _line(anchor_id: str, x: float, y: float, width: float) -> BuildAnchor:
    kind = AnchorKind.date if "." in anchor_id else AnchorKind.sign
    return BuildAnchor(anchor_id, kind, 1, x, y, width)


def application_lines(*, lang: str = "ru", consultant: bool = False, academic: bool = False) -> tuple[BuildAnchor, ...]:
    """Линии «Заявления» (15.15): английская шапка короче на 28,8 мм; строка консультанта сдвигает академрука."""
    shift = 0.0 if lang == "ru" else -28.8
    lines = [_line("supervisor", 169.5, 186.8 + shift, 25.5), _line("author", 161.0, 212.3 + shift, 34.0)]
    row = 225.9 + shift
    if consultant:
        lines.append(_line("co_supervisor", 169.5, row, 25.5))
        row += 18.2
    if academic:
        lines.append(_line("academic_supervisor", 169.5, row, 25.5))
    return tuple(lines)


def proposal_lines(*, lang: str = "ru", title_rows: int = 1) -> tuple[BuildAnchor, ...]:
    """Строка 6 «Описания проекта»: якорь подписи в начале строки даты; длинное название сдвигает её вниз."""
    y = (153.0 if lang == "ru" else 131.0) + 6.0 * (title_rows - 1)
    if lang == "ru":
        return (
            _line("supervisor", 81.7, y, 0.0),
            _line("supervisor.day", 81.7, y, 8.0),
            _line("supervisor.month_word", 92.6, y, 25.0),
        )
    return (
        _line("supervisor", 79.7, y, 0.0),
        _line("supervisor.day", 79.7, y, 8.0),
        _line("supervisor.month_number", 88.7, y, 8.0),
    )


def build(project: Project, doc_id: str, lines: tuple[BuildAnchor, ...] | None, text: str = "v1") -> str:
    """Сборка документа: PDF на месте результата и, если `lines` не None, якоря этой сборки (иначе их нет: раннер
    прежней версии или шаблон без якорей). Возвращает sha256 PDF."""
    project.build(doc_id, text)
    doc = project.call(project.owner, "GET", f"{project.base}/documents/{doc_id}").json()
    pdf = project.folder / doc["output_file"]
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    source = PurePosixPath(doc["source_file"])
    anchors = project.folder / source.parent / ".build" / doc_id / f"{source.stem}.anchors.json"
    if lines is None:
        anchors.unlink(missing_ok=True)
        return sha
    anchors.parent.mkdir(parents=True, exist_ok=True)
    anchors.write_bytes(encode_anchors(BuildAnchors(sha, lines)))
    return sha


def build_anchor_packs(target: Path) -> Path:
    """Копия паков репозитория с выпущенной patch-версией `ANCHOR_VERSION` с местами на якорях."""
    shutil.copytree(REPO_PACKS, target)
    template_dir = target / "hse-cs-sse" / "templates" / "coursework"
    version_dir = template_dir / "versions" / ANCHOR_VERSION
    shutil.copytree(template_dir / "versions" / RELEASED_VERSION, version_dir)
    shutil.copyfile(MACROS, version_dir / "files" / "common" / "anchors.tex")
    manifest_path = version_dir / "version.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = ANCHOR_VERSION
    manifest["released_at"] = "2026-11-14"
    manifest["signatures"]["anchor_macros"] = ["hseSignField", "signdateblank"]
    for slot in manifest["signatures"]["slots"]:
        slot.update(_ANCHOR_SLOTS.get(slot["id"], {}))
    for profile in manifest["pack_submission"]["profiles"]:
        if profile["id"] == "topic-approval":
            profile["signing_slots"] = _SIGNING_SLOTS
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    freeze(template_dir, ANCHOR_VERSION, TemplateUpdateClass.patch)
    return target


@pytest.fixture
def anchor_packs(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    packs = build_anchor_packs(tmp_path_factory.mktemp("anchors") / "packs")
    monkeypatch.setattr(settings, "packs_dir", packs)
    return packs
