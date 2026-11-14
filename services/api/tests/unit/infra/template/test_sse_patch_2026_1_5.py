"""`hse-cs-sse/coursework` 2026.1.5 укладывается в исключение класса patch к 2026.1.4 (signing-route.md, 15.10).

Манифест отличается только сведениями о подписании (места и метки даты слотов, обёртки якорей, пресеты точек,
порядок маршрута) и подсказками сроков, а файлы шаблона только якорями мест: `common/anchors.tex` (копия эталона
Студии) и вызовы якорей в исходниках документов с подписями. Что PDF при этом тот же байт в байт, проверяет TeX-тест
`tests/integration/tex/test_sse_anchor_presets.py`.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import hse_doc_studio.infra.compile as compile_pkg
import yaml
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.template_versions import classify_update
from hse_doc_studio.infra.template.releases import load_releases

TEMPLATE = Path(__file__).resolve().parents[6] / "packs" / "hse-cs-sse" / "templates" / "coursework"
BEFORE, AFTER = "2026.1.4", "2026.1.5"
MACROS = Path(compile_pkg.__file__).parent / "tex" / "anchors.tex"

# Ключи исключения (15.10, 15.17.7) и служебные поля версии.
_VERSION_KEYS = ("id", "released_at", "changes")
_SIGNATURE_KEYS = ("anchor_macros", "route")
_SLOT_KEYS = ("placements", "default_dates", "default_placement")
_PROFILE_KEYS = ("signing_slots", "signing_route", "deadline_hint")

# Файлы с якорями: исходники документов точек с подписями и общий макрос строки даты.
_ANCHORED_FILES = {
    "common/meta.tex.j2",
    "topic_application/topic_application.tex",
    "project_proposal/preamble.tex",
    "project_proposal/project_proposal.ru.tex",
    "project_proposal/project_proposal.en.tex",
    "report/preamble.tex",
    "report/title.ru.tex",
    "report/title.en.tex",
}


def _manifest(version: str) -> dict[str, Any]:
    return dict(yaml.safe_load((TEMPLATE / "versions" / version / "version.yaml").read_text(encoding="utf-8")))


def _without_exception_keys(manifest: dict[str, Any]) -> dict[str, Any]:
    stripped = copy.deepcopy(manifest)
    for key in _VERSION_KEYS:
        stripped.pop(key, None)
    signatures = stripped.get("signatures", {})
    for key in _SIGNATURE_KEYS:
        signatures.pop(key, None)
    for slot in signatures.get("slots", []):
        for key in _SLOT_KEYS:
            slot.pop(key, None)
    for profile in stripped.get("pack_submission", {}).get("profiles", []):
        for key in _PROFILE_KEYS:
            profile.pop(key, None)
    return stripped


def _files(version: str) -> dict[str, bytes]:
    root = TEMPLATE / "versions" / version
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".DS_Store" and path.name != "version.yaml"
    }


def test__2026_1_5__released_as_a_patch_of_2026_1_4_and_default() -> None:
    releases = load_releases(TEMPLATE)
    template = yaml.safe_load((TEMPLATE / "template.yaml").read_text(encoding="utf-8"))

    assert releases[AFTER].kind is TemplateUpdateClass.patch
    assert classify_update(BEFORE, AFTER) is TemplateUpdateClass.patch
    assert _manifest(AFTER)["release"] == {"kind": "patch"}
    assert template["default_version"] == AFTER


def test__2026_1_5__manifest_differs_only_in_signing_presets_and_deadline_hints() -> None:
    before, after = _manifest(BEFORE), _manifest(AFTER)

    assert _without_exception_keys(after) == _without_exception_keys(before)
    # Пресеты появились, а не только пропали: у точки заявки слоты сверх точки и порядок, у всех точек подсказки.
    profiles = {p["id"]: p for p in after["pack_submission"]["profiles"]}
    assert {s["slot_id"] for s in profiles["topic-approval"]["signing_slots"]} == {
        "co_supervisor",
        "academic_supervisor",
    }
    assert all(set(p["deadline_hint"]) == {"ru", "en"} for p in profiles.values())


def test__2026_1_5__files_differ_only_in_anchors() -> None:
    before, after = _files(BEFORE), _files(AFTER)

    assert set(after) - set(before) == {"files/common/anchors.tex"}
    assert after["files/common/anchors.tex"] == MACROS.read_bytes()
    assert set(before) - set(after) == set()
    changed = {path.removeprefix("files/") for path in before if before[path] != after[path]}
    assert changed == _ANCHORED_FILES
    for path in changed:
        text = after[f"files/{path}"].decode("utf-8")
        assert "\\hseSignAnchor" in text or "\\hseDateAnchor" in text or "\\input{../common/anchors}" in text, path
