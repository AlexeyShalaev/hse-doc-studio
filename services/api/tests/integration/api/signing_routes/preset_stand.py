"""Каталог шаблонов с пресетом маршрута для серверных тестов (docs/design/signing-route.md, 15.10).

Копия настоящих паков и в ней `hse-cs-sse/coursework` 2026.1.4: те же файлы, что 2026.1.3, и ключи пресета в
`version.yaml` (места по документам, метки даты научрука на «Описании проекта», консультант и академрук на
«Заявлении» по условию), выпущена patch-версией. Настоящая 2026.1.4 выходит срезом R27, координаты здесь те же, что в
таблице 15.10.

Фикстуру `preset_packs` тест берёт раньше `stand`: приложение стенда читает каталог шаблонов при создании.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.infra.template.releases import freeze

REPO_PACKS = Path(__file__).resolve().parents[6] / "packs"
PRESET_VERSION = "2026.1.4"
RELEASED_VERSION = "2026.1.3"

_PRESET_SLOTS: dict[str, dict[str, Any]] = {
    "supervisor": {
        "placements": {
            "project_proposal": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 40},
            "topic_application": {"page": 1, "x_mm": 163, "y_mm": 168, "width_mm": 40},
        },
        "default_dates": {
            "project_proposal": [
                {"page": 1, "x_mm": 81, "y_mm": 156, "width_mm": 7, "height_mm": 5, "format": "day"},
                {"page": 1, "x_mm": 90, "y_mm": 156, "width_mm": 24, "height_mm": 5, "format": "month_word"},
            ]
        },
    },
    "author": {"placements": {"topic_application": {"page": 1, "x_mm": 165, "y_mm": 200, "width_mm": 30}}},
    "co_supervisor": {"placements": {"topic_application": {"page": 1, "x_mm": 165, "y_mm": 222, "width_mm": 28}}},
    "academic_supervisor": {"placements": {"topic_application": {"page": 1, "x_mm": 168, "y_mm": 238, "width_mm": 28}}},
}
_SIGNING_SLOTS = [
    {"doc_id": "topic_application", "slot_id": "co_supervisor", "when": {"person": "co_supervisor"}},
    {
        "doc_id": "topic_application",
        "slot_id": "academic_supervisor",
        "when": {"person": "supervisor", "role": "company"},
    },
]


def build_preset_packs(target: Path) -> Path:
    """Копия паков репозитория с выпущенной patch-версией 2026.1.4 `hse-cs-sse/coursework` с пресетом."""
    shutil.copytree(REPO_PACKS, target)
    template_dir = target / "hse-cs-sse" / "templates" / "coursework"
    version_dir = template_dir / "versions" / PRESET_VERSION
    shutil.copytree(template_dir / "versions" / RELEASED_VERSION, version_dir)
    manifest_path = version_dir / "version.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = PRESET_VERSION
    manifest["released_at"] = "2026-11-14"
    for slot in manifest["signatures"]["slots"]:
        slot.update(_PRESET_SLOTS.get(slot["id"], {}))
    for profile in manifest["pack_submission"]["profiles"]:
        if profile["id"] == "topic-approval":
            profile["signing_slots"] = _SIGNING_SLOTS
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    freeze(template_dir, PRESET_VERSION, TemplateUpdateClass.patch)
    return target


@pytest.fixture
def preset_packs(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    packs = build_preset_packs(tmp_path_factory.mktemp("preset") / "packs")
    monkeypatch.setattr(settings, "packs_dir", packs)
    return packs
