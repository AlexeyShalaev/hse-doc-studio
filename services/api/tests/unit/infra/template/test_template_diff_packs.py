"""Классификатор изменений на реальных паках репозитория (template-studio.md, 7.2 и 15).

Цепочки версий дают ожидаемые причины, а patch-версии, выпущенные по исключению 15.10 (signing-route.md), этим
исключением и объясняются. Здесь же проверка R27 для `hse-cs-sse/coursework` 2026.1.5: манифест отличается от 2026.1.4
только заготовками подписания и подсказками сроков, а файлы шаблона только якорями мест (`common/anchors.tex`, копия
эталона Студии, и вызовы якорей в исходниках документов с подписями). Что PDF при этом тот же байт в байт, проверяет
TeX-тест `tests/integration/tex/test_sse_anchor_presets.py`.
"""

from __future__ import annotations

from pathlib import Path

import hse_doc_studio.infra.compile as compile_pkg
import pytest
import yaml
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.template_diff import ChangeReport, classify_change
from hse_doc_studio.infra.template.releases import load_releases

PACKS = Path(__file__).resolve().parents[6] / "packs"
SSE = PACKS / "hse-cs-sse" / "templates" / "coursework"
MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"
PATCH, MINOR = TemplateUpdateClass.patch, TemplateUpdateClass.minor


def _report(template: Path, base: str, new: str) -> ChangeReport:
    return classify_change(template / "versions" / base, template / "versions" / new)


def _codes(report: ChangeReport) -> set[str]:
    return {reason.code for reason in report.reasons}


@pytest.mark.parametrize(
    ("template", "base", "new", "suggested", "codes"),
    [
        (SSE, "2026.1", "2026.1.1", PATCH, {"file_changed"}),
        (SSE, "2026.1.1", "2026.1.2", PATCH, {"text", "file_changed"}),
        # Сужение `methods` patch-версией: мягкое правило предлагает minor, минимум patch (7.2).
        (SSE, "2026.1.2", "2026.1.3", MINOR, {"methods"}),
        (SSE, "2026.1.3", "2026.1.4", PATCH, {"text", "optional_field_added", "file_changed"}),
        # Пресеты на якорях; `default_placement` слотов консультанта и академрука перешёл на якорь (тоже исключение).
        (
            SSE,
            "2026.1.4",
            "2026.1.5",
            PATCH,
            {"signing_preset", "deadline_hint", "file_added", "file_changed"},
        ),
        (
            PACKS / "hse-cs-se" / "templates" / "coursework",
            "2026.1",
            "2026.1.1",
            PATCH,
            {"text", "optional_field_added", "file_changed"},
        ),
        (
            PACKS / "hse-cs-se" / "templates" / "vkr",
            "2026.1",
            "2026.1.1",
            PATCH,
            {"text", "optional_field_added", "file_changed"},
        ),
    ],
    ids=["sse-1.1", "sse-1.2", "sse-1.3", "sse-1.4", "sse-1.5", "se-coursework-1.1", "se-vkr-1.1"],
)
def test__real_chains__give_the_expected_reasons(
    template: Path, base: str, new: str, suggested: TemplateUpdateClass, codes: set[str]
) -> None:
    report = _report(template, base, new)

    assert report.minimum is PATCH
    assert report.suggested is suggested
    assert _codes(report) == codes
    assert report.by_number is PATCH


# ── R27: 2026.1.5 к 2026.1.4 укладывается в исключение patch ──


def test__sse_2026_1_5__released_as_a_patch_of_2026_1_4_and_default() -> None:
    manifest = yaml.safe_load((SSE / "versions" / "2026.1.5" / "version.yaml").read_text(encoding="utf-8"))
    template = yaml.safe_load((SSE / "template.yaml").read_text(encoding="utf-8"))

    assert load_releases(SSE)["2026.1.5"].kind is PATCH
    assert manifest["release"] == {"kind": "patch"}
    assert template["default_version"] == "2026.1.5"


def test__sse_2026_1_5__manifest_differs_only_in_signing_presets_and_deadline_hints() -> None:
    report = _report(SSE, "2026.1.4", "2026.1.5")

    assert report.minimum is PATCH
    assert report.suggested is PATCH
    manifest_reasons = [r for r in report.reasons if not r.path.startswith("files/")]

    assert all(r.exception for r in manifest_reasons), [r.path for r in manifest_reasons if not r.exception]
    assert {r.path for r in manifest_reasons if r.path.endswith("default_placement")} == {
        "signatures.slots[co_supervisor].default_placement",
        "signatures.slots[academic_supervisor].default_placement",
    }
    # Пресеты появились, а не только пропали: у точки заявки слоты сверх точки и порядок, у всех точек подсказки.
    exception_paths = {r.path for r in manifest_reasons if r.exception}
    assert {
        "pack_submission.profiles[topic-approval].signing_slots",
        "pack_submission.profiles[topic-approval].signing_route",
        "signatures.anchor_macros",
    } <= exception_paths
    assert {p for p in exception_paths if p.endswith("deadline_hint")} == {
        f"pack_submission.profiles[{p}].deadline_hint"
        for p in ("topic-approval", "extended-proposal", "pre-defence", "final")
    }
    assert all(r.change == "added" for r in manifest_reasons if not r.path.endswith("default_placement"))


def test__sse_2026_1_5__files_differ_only_in_anchors() -> None:
    report = _report(SSE, "2026.1.4", "2026.1.5")
    by_code: dict[str, set[str]] = {}
    for reason in report.reasons:
        if reason.path.startswith("files/"):
            by_code.setdefault(reason.code, set()).add(reason.path.removeprefix("files/"))

    assert by_code.pop("file_added") == {"common/anchors.tex"}
    assert (SSE / "versions" / "2026.1.5" / "files" / "common" / "anchors.tex").read_bytes() == MACROS.read_bytes()
    changed = by_code.pop("file_changed")
    assert by_code == {}
    assert changed == {
        "common/meta.tex.j2",
        "topic_application/topic_application.tex",
        "project_proposal/preamble.tex",
        "project_proposal/project_proposal.ru.tex",
        "project_proposal/project_proposal.en.tex",
        "report/preamble.tex",
        "report/title.ru.tex",
        "report/title.en.tex",
    }
    for path in changed:
        text = (SSE / "versions" / "2026.1.5" / "files" / path).read_text(encoding="utf-8")
        assert "\\hseSignAnchor" in text or "\\hseDateAnchor" in text or "\\input{../common/anchors}" in text, path
