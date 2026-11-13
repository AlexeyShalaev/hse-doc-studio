"""Места на якорях в паке: лоадер и `pack_lint` (docs/design/signing-route.md, 15.17.7 и 15.17.13)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import hse_doc_studio.infra.compile as compile_pkg
import pytest
import yaml
from hse_doc_studio.core.catalog import AnchorDate, AnchorPlace, SignatureDefaultDate, SignatureDefaultPlacement
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat
from hse_doc_studio.infra.template.pack_lint import lint_version_dir
from hse_doc_studio.infra.template.yaml_template_repository import (
    _parse_signature_slot,
    parse_anchor_macros,
    parse_default_dates,
    parse_slot_placement,
)

MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"

# --- лоадер ---


def test__parse_slot_placement__anchor_with_defaults() -> None:
    assert parse_slot_placement({"anchor": "supervisor"}, "placements.t") == AnchorPlace("supervisor")


def test__parse_slot_placement__anchor_with_offsets_and_fallback() -> None:
    place = parse_slot_placement(
        {"anchor": "author", "align": "right", "dx_mm": 1, "dy_mm": -11, "width_mm": 30, "x_mm": 165, "y_mm": 201},
        "placements.t",
    )

    assert place == AnchorPlace(
        "author",
        align=DateMarkAlign.right,
        dx_mm=1.0,
        dy_mm=-11.0,
        width_mm=30.0,
        fallback=SignatureDefaultPlacement(page=1, x_mm=165, y_mm=201, width_mm=30),
    )


@pytest.mark.parametrize(
    ("item", "fragment"),
    [
        ({"anchor": "Supervisor"}, "not an anchor id"),
        ({"anchor": "supervisor", "align": "middle"}, "align"),
        ({"anchor": "supervisor", "width_mm": 5}, "width_mm 5"),
        ({"anchor": "supervisor", "dx_mm": 300}, "dx_mm 300"),
        ({"anchor": "supervisor", "dy_mm": -300}, "dy_mm -300"),
        ({"anchor": "supervisor", "x_mm": 10, "y_mm": 10}, "width_mm"),
    ],
)
def test__parse_slot_placement__anchor_wrong__error(item: dict[str, Any], fragment: str) -> None:
    with pytest.raises((TypeError, ValueError, KeyError), match=fragment):
        parse_slot_placement(item, "placements.t")


def test__parse_default_dates__anchored_marks_format_from_the_part() -> None:
    parsed = parse_default_dates(
        {
            "project_proposal": [
                {"anchor": "supervisor.day"},
                {"anchor": "supervisor.month_word", "height_mm": 6, "align": "left"},
                {"anchor": "supervisor.day", "format": "date_numeric", "width_mm": 20, "x_mm": 30, "y_mm": 40},
            ]
        }
    )

    assert parsed == (
        (
            "project_proposal",
            (
                AnchorDate("supervisor.day", DateMarkFormat.day),
                AnchorDate("supervisor.month_word", DateMarkFormat.month_word, height_mm=6, align=DateMarkAlign.left),
                AnchorDate(
                    "supervisor.day",
                    DateMarkFormat.date_numeric,
                    width_mm=20,
                    fallback=SignatureDefaultDate(1, 30, 40, 20, 5, DateMarkFormat.date_numeric),
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    "item",
    [
        {"anchor": "supervisor"},  # у метки даты якорь с частью
        {"anchor": "supervisor.line"},  # часть не формат, а формата нет
        {"anchor": "supervisor.day", "height_mm": 30},
    ],
)
def test__parse_default_dates__anchored_mark_wrong__error(item: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        parse_default_dates({"project_proposal": [item]})


def test__parse_signature_slot__broken_anchored_mark_dropped_alone() -> None:
    slot = _parse_signature_slot(
        {
            "id": "supervisor",
            "applies_to": ["project_proposal"],
            "default_dates": {"project_proposal": [{"anchor": "supervisor"}, {"anchor": "supervisor.day"}]},
            "placements": {"project_proposal": {"anchor": "bad name"}, "report": {"anchor": "supervisor"}},
        }
    )

    assert slot.dates_for("project_proposal") == (AnchorDate("supervisor.day", DateMarkFormat.day),)
    assert slot.placements == (("report", AnchorPlace("supervisor")),)


def test__parse_signature_slot__anchored_default_placement_needs_the_fallback() -> None:
    full = _parse_signature_slot(
        {
            "id": "supervisor",
            "applies_to": ["report"],
            "default_placement": {"anchor": "supervisor", "page": 1, "x_mm": 110, "y_mm": 130, "width_mm": 40},
        }
    )
    bare = _parse_signature_slot(
        {"id": "supervisor", "applies_to": ["report"], "default_placement": {"anchor": "supervisor"}}
    )

    assert full.default_anchor is not None
    assert full.default_placement == SignatureDefaultPlacement(1, 110, 130, 40)
    assert full.entry_for("report") == full.default_anchor
    # Без запасного места запись отбрасывается: прежняя Студия потеряла бы место совсем.
    assert bare.default_anchor is None
    assert bare.entry_for("report") == bare.default_placement


def test__parse_anchor_macros__names_with_or_without_backslash() -> None:
    assert parse_anchor_macros(["hseSignField", "\\signdateblank"]) == ("hseSignField", "signdateblank")
    with pytest.raises(ValueError, match="not TeX macro names"):
        parse_anchor_macros(["sign_field"])


# --- линтер ---

_APPLICATION = r"""\documentclass{article}
\input{../common/meta}
\input{../common/anchors}
\newcommand\hseSignField[2][]{\hseSignAnchor[#2]{#1}\rule{#2}{0.4pt}}
\begin{document}
\hseSignField[supervisor]{40mm}
\hseSignAnchor[30mm]{author}\rule{30mm}{0.4pt}
\end{document}
"""
_META = r"""\newcommand\signdateblank[1][supervisor]{\hseDateAnchor[8mm]{#1}{day}\rule{8mm}{0.4pt}
  \hseDateAnchor[25mm]{#1}{month_word}\rule{25mm}{0.4pt}}
"""
_PROPOSAL = r"""\documentclass{article}
\input{../common/meta}
\input{../common/anchors}
\begin{document}
\hseSignAnchor{supervisor}\signdateblank[supervisor]
\end{document}
"""


def _manifest(**signatures: Any) -> dict[str, Any]:
    supervisor = {
        "id": "supervisor",
        "applies_to": ["project_proposal", "topic_application"],
        "placements": {
            "topic_application": {"anchor": "supervisor", "align": "right", "width_mm": 28},
            "project_proposal": {"anchor": "supervisor", "align": "left", "dy_mm": -14, "width_mm": 40},
        },
        "default_dates": {
            "project_proposal": [{"anchor": "supervisor.day"}, {"anchor": "supervisor.month_word"}],
        },
    }
    author = {
        "id": "author",
        "applies_to": ["topic_application"],
        "placements": {"topic_application": {"anchor": "author", "align": "right", "dy_mm": -11, "width_mm": 30}},
    }
    return {
        "langs": ["ru", "en"],
        "documents": [
            {"id": "project_proposal", "source_file": "project_proposal/main.tex"},
            {"id": "topic_application", "source_file": "topic_application/main.tex"},
        ],
        "signatures": {"anchor_macros": ["hseSignField", "signdateblank"], "slots": [author, supervisor], **signatures},
    }


def _write(
    version_dir: Path, manifest: dict[str, Any], *, macros: bool = True, sources: dict[str, str] | None = None
) -> Path:
    files = version_dir / "files"
    texts = {
        "topic_application/main.tex": _APPLICATION,
        "project_proposal/main.tex": _PROPOSAL,
        "common/meta.tex": _META,
        **(sources or {}),
    }
    for rel, text in texts.items():
        (files / rel).parent.mkdir(parents=True, exist_ok=True)
        (files / rel).write_text(text, encoding="utf-8")
    if macros:
        shutil.copyfile(MACROS, files / "common" / "anchors.tex")
    (version_dir / "version.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return version_dir


def _anchor_errors(version_dir: Path) -> list[str]:
    return [e for e in lint_version_dir(version_dir).errors if "якор" in e or "anchor" in e]


def test__lint__anchors_by_calls_and_wrappers__no_errors_no_warnings(tmp_path: Path) -> None:
    report = lint_version_dir(_write(tmp_path, _manifest()))

    assert report.errors == []
    assert [w for w in report.warnings if "якор" in w] == []


def test__lint__anchor_not_in_the_document_sources__error(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["signatures"]["slots"][1]["placements"]["topic_application"]["anchor"] = "co_supervisor"

    errors = _anchor_errors(_write(tmp_path, manifest))

    assert len(errors) == 1
    assert "placements.topic_application" in errors[0]
    assert "'co_supervisor'" in errors[0]


def test__lint__wrapper_not_listed_in_anchor_macros__its_anchor_not_seen(tmp_path: Path) -> None:
    errors = _anchor_errors(_write(tmp_path, _manifest(anchor_macros=["signdateblank"])))

    assert any("placements.topic_application" in e and "'supervisor'" in e for e in errors)


def test__lint__date_part_of_the_wrapper_definition(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["signatures"]["slots"][1]["default_dates"]["project_proposal"].append({"anchor": "supervisor.year"})

    errors = _anchor_errors(_write(tmp_path, manifest))

    expected = (
        "signatures.slots[supervisor]: default_dates.project_proposal: якоря 'supervisor.year' нет в исходниках "
        "документа project_proposal и в common/ (\\hseSignAnchor, \\hseDateAnchor или обёртка из anchor_macros)"
    )
    assert errors == [expected]


def test__lint__macros_file_missing_or_not_included__error(tmp_path: Path) -> None:
    no_file = _anchor_errors(_write(tmp_path / "a", _manifest(), macros=False))
    not_included = _anchor_errors(
        _write(
            tmp_path / "b",
            _manifest(),
            sources={"project_proposal/main.tex": _PROPOSAL.replace("\\input{../common/anchors}\n", "")},
        )
    )

    assert any("common/anchors.tex" in e and "нет" in e for e in no_file)
    assert any("project_proposal" in e and "не подключает" in e for e in not_included)


def test__lint__anchored_default_placement_without_fallback__error(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["signatures"]["slots"][0]["default_placement"] = {"anchor": "author"}

    errors = lint_version_dir(_write(tmp_path, manifest)).errors

    assert any("default_placement" in e and "page, x_mm, y_mm and width_mm" in e for e in errors)


def test__lint__unknown_name_and_repeated_anchor__warnings(tmp_path: Path) -> None:
    application = _APPLICATION.replace(
        "\\end{document}", "\\hseSignAnchor{supervsior}\\hseSignAnchor[30mm]{author}\n\\end{document}"
    )

    warnings = lint_version_dir(
        _write(tmp_path, _manifest(), sources={"topic_application/main.tex": application})
    ).warnings

    assert any("'supervsior'" in w and "опечатка" in w for w in warnings)
    assert any("'author'" in w and "2 раза" in w for w in warnings)


def test__lint__anchor_in_a_comment__not_seen(tmp_path: Path) -> None:
    application = _APPLICATION.replace("\\hseSignAnchor[30mm]{author}", "% \\hseSignAnchor[30mm]{author}")

    errors = _anchor_errors(_write(tmp_path, _manifest(), sources={"topic_application/main.tex": application}))

    assert any("'author'" in e for e in errors)
