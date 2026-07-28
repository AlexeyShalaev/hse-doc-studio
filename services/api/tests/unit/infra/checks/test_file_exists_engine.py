"""Поиск обязательного файла, когда документ принадлежит автору команды.

Движок форм пишет ответы пер-автор (`ai_declaration--shalaev.json`), а правило
в паке называет файл одним именем. Без развёртки суффикса проверка в командной
работе не находила файл никогда — сколько бы форм автор ни заполнил.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.file_exists_engine import FileExistsCheckEngine

from tests.factories import make_check_rule

RULE_PATH = ".hse-studio/forms/ai_declaration.json"


@pytest.fixture
def engine() -> FileExistsCheckEngine:
    return FileExistsCheckEngine()


@pytest.fixture
def rule() -> CheckRule:
    return make_check_rule(
        rule_id="hse-pi-methodology-2026/ai-declaration-required",
        engine=CheckEngine.file_exists,
        params={"path": RULE_PATH},
    )


@pytest.fixture
def forms_dir(tmp_path: Path) -> Path:
    target = tmp_path / ".hse-studio" / "forms"
    target.mkdir(parents=True)
    return target


def run(engine: FileExistsCheckEngine, rule: CheckRule, project: Path, doc_id: str) -> list:
    return engine.run(
        rule=rule,
        severity=CheckSeverity.warn,
        project_folder=project,
        doc_id=doc_id,
        source_file="thesis/thesis.tex",
        log_content=None,
    )


def test__file_exists__solo_project_with_the_file__passes(
    engine: FileExistsCheckEngine, rule: CheckRule, tmp_path: Path, forms_dir: Path
) -> None:
    (forms_dir / "ai_declaration.json").write_text("{}", encoding="utf-8")

    assert run(engine, rule, tmp_path, "thesis") == []


def test__file_exists__solo_project_without_the_file__reports(
    engine: FileExistsCheckEngine, rule: CheckRule, tmp_path: Path, forms_dir: Path
) -> None:
    assert len(run(engine, rule, tmp_path, "thesis")) == 1


def test__file_exists__team_document_with_its_authors_file__passes(
    engine: FileExistsCheckEngine, rule: CheckRule, tmp_path: Path, forms_dir: Path
) -> None:
    (forms_dir / "ai_declaration--shalaev.json").write_text("{}", encoding="utf-8")

    assert run(engine, rule, tmp_path, "thesis--shalaev") == []


def test__file_exists__team_document_when_only_the_other_author_filled_it__reports(
    engine: FileExistsCheckEngine, rule: CheckRule, tmp_path: Path, forms_dir: Path
) -> None:
    # Заполненная форма соавтора не закрывает требование к этому автору.
    (forms_dir / "ai_declaration--ivanov.json").write_text("{}", encoding="utf-8")

    assert len(run(engine, rule, tmp_path, "thesis--shalaev")) == 1


def test__file_exists__team_document_with_a_shared_file__passes(
    engine: FileExistsCheckEngine, rule: CheckRule, tmp_path: Path, forms_dir: Path
) -> None:
    # Общий файл означает «заполнено на всех» — тоже засчитывается.
    (forms_dir / "ai_declaration.json").write_text("{}", encoding="utf-8")

    assert run(engine, rule, tmp_path, "thesis--shalaev") == []
