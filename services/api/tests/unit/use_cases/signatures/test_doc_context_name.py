"""Имя файла документа у открепленных подписей: у личного документа команды с фамилией владельца на языке проекта."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.preview import auto_examples, resolve_combination, switches_for, synthetic_project
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.use_cases.pack_studio.synthetic_project import synthetic_core_project
from hse_doc_studio.use_cases.signatures._doc_context import load_doc_context

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic


@pytest.fixture(scope="module")
def version(tmp_path_factory: pytest.TempPathFactory) -> TemplateVersion:
    return load_synthetic(tmp_path_factory.mktemp("packs"))


class _Get:
    def __init__(self, project: Any) -> None:
        self.project = project

    async def execute(self, _inp: Any) -> Any:
        return SimpleNamespace(project=self.project)


class _Repo:
    def __init__(self, version: TemplateVersion) -> None:
        self.version = version

    def get_version(self, *_ref: str) -> TemplateVersion:
        return self.version


@pytest.mark.parametrize(
    ("lang", "names"),
    [("ru", ["Отчёт — Иванов", "Отчёт — Петрова"]), ("en", ["Report — Ivanov", "Report — Petrova"])],
)
async def test__base_name__team_personal_document__carries_the_surname(
    version: TemplateVersion, lang: str, names: list[str]
) -> None:
    combo = resolve_combination(switches_for(version), {"kind": "project", "staffing": "team2", "lang": lang})
    synthetic = synthetic_project(version, auto_examples(version)[0], combo, date(2026, 11, 16))
    project = synthetic_core_project("p", "t", version, synthetic)
    project.folder = Path("/nowhere")
    reports = [d.id for d in project.documents if d.def_id == "report"]

    found = [
        (
            await load_doc_context(
                _Get(project),  # type: ignore[arg-type]
                _Repo(version),  # type: ignore[arg-type]
                ProjectTemplateService(),
                project.id,
                doc_id,
            )
        ).base_name
        for doc_id in reports
    ]

    assert found == names
