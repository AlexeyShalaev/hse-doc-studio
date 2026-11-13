"""Эталон макросов якорей `infra/compile/tex/anchors.tex` и копии `common/anchors.tex` в паках (15.17.3).

На настоящем TeX макросы проверяет `tests/integration/tex/test_build_anchors.py`; здесь то, что видно без TeX.
"""

from __future__ import annotations

from pathlib import Path

import hse_doc_studio.infra.compile as compile_pkg
import pytest
from hse_doc_studio.infra.project_init.template_renderer import _render_text

MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"
PACKS = Path(__file__).resolve().parents[5] / "packs"


def test__macros__define_both_anchors_and_write_the_positions_file() -> None:
    text = MACROS.read_text(encoding="utf-8")

    assert r"\newcommand\hseSignAnchor[2][0pt]" in text
    assert r"\newcommand\hseDateAnchor[3][0pt]" in text
    assert r"\openout\hse@posfile=\jobname.hsepos" in text
    assert r"hsepos 1 \number\paperwidth\space\number\paperheight" in text
    # Позиция в том же проходе: `\savepos` и отложенный `\write`, без `zref` и `.aux`.
    assert "zref" not in text
    assert r"\tex_savepos:D" in text


def test__macros__survive_project_init_rendering_byte_for_byte() -> None:
    # Файлы пака `.tex` проходят через Jinja при создании проекта: `{#1}` и `}}` не должны его задеть.
    text = MACROS.read_text(encoding="utf-8")

    assert _render_text(text, {"project": {}}, MACROS) == text


@pytest.mark.parametrize("copy", sorted(PACKS.glob("*/templates/*/versions/*/files/common/anchors.tex")), ids=str)
def test__pack_copy__same_as_the_reference(copy: Path) -> None:
    # Пак кладёт копию эталона байт в байт: разбор файла позиций в Студии знает только этот формат.
    assert copy.read_bytes() == MACROS.read_bytes()
