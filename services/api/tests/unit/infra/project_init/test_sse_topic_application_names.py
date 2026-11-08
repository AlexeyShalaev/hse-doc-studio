"""Заявление о теме КП СПИ: колонка «Фамилия И.О.» по бланку SmartLMS («Шершаков С.А.»)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.infra.project_init.template_renderer import _render_text

_META = (
    Path(__file__).resolve().parents[6]
    / "packs/hse-cs-sse/templates/coursework/versions/2026.1.2/files/common/meta.tex.j2"
)


def _short_names(project: dict[str, Any]) -> dict[str, str]:
    rendered = _render_text(_META.read_text(encoding="utf-8"), {"project": project, "author": {}}, _META)
    return dict(re.findall(r"\\newcommand\{\\hse(\w+)ShortName\}\{%\n(.*)\}", rendered))


@pytest.mark.parametrize(
    "name",
    ["П. П. Петров", "П.П. Петров", "Петров Пётр Петрович", "Петров П. П.", "Петров П.П.", "  Петров  Пётр  Петрович "],
)
def test__short_name__any_input_order__surname_then_initials(name: str) -> None:
    person = {"name": name}

    names = _short_names({"supervisor": person, "co_supervisor": person, "academic_supervisor": person})

    assert names == {"Supervisor": "Петров П.П.", "CoSupervisor": "Петров П.П.", "AcademicSupervisor": "Петров П.П."}


def test__short_name__unset__academic_default_and_supervisor_placeholder() -> None:
    names = _short_names({})

    assert names == {
        "Supervisor": r"\hseFill{ФИО научного руководителя}",
        "CoSupervisor": "",
        "AcademicSupervisor": "Шершаков С.А.",
    }


def test__short_name__single_word_and_tex_specials__kept_and_escaped() -> None:
    names = _short_names({"supervisor": {"name": "Петров"}, "co_supervisor": {"name": "П. Петров_2"}})

    assert names["Supervisor"] == "Петров"
    assert names["CoSupervisor"] == r"Петров\_2 П."


def test__academic_supervisor_full_name__other_documents_keep_the_old_format() -> None:
    rendered = _render_text(_META.read_text(encoding="utf-8"), {"project": {}, "author": {}}, _META)

    assert "\\newcommand{\\hseAcademicSupervisorName}{%\nС. А. Шершаков}" in rendered
