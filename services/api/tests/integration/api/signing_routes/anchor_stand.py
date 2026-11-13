"""Пак с местами на якорях шаблона для серверных тестов (docs/design/signing-route.md, 15.17): настоящая 2026.1.5.

Выпущенная `hse-cs-sse/coursework` 2026.1.5 (R27): `common/anchors.tex`, якоря в заявлении, «Описании проекта» и на
титуле отчёта, пресет 15.10 на якорях (`align`, `dx_mm`, `dy_mm`) с запасными местами в мм по замерам 2026.1.4.
Сборку заменяет PDF на месте результата и `anchors.json` его сборки в `.build`, как их оставляет публикация сборки;
линии взяты из сборки 2026.1.5 на TeX Live (15.15, `tests/integration/tex/test_sse_anchor_presets.py`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors, encode_anchors

from tests.integration.api.signing_routes.preset_stand import REPO_PACKS

if TYPE_CHECKING:
    # Стенд тянет модели сервера: без extra server модуль собирается, а импорт только для типов.
    from tests.integration.api.signing_routes.stand import Project

ANCHOR_VERSION = "2026.1.5"


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
            _line("supervisor", 79.7, y, 0.0),
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


@pytest.fixture
def anchor_packs(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Паки репозитория: 2026.1.5 выпущена, копия не нужна (тесты пак не меняют)."""
    monkeypatch.setattr(settings, "packs_dir", REPO_PACKS)
    return REPO_PACKS
