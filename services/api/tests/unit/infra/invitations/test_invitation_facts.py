"""Данные проекта для текста приглашения: люди и тема из project.json, вид работы и документы из пака."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EngineType, Lang, PersonRole
from hse_doc_studio.core.invitations.message import ProjectPerson
from hse_doc_studio.core.value_objects import Author, Person, ProjectLock
from hse_doc_studio.infra.invitations.facts import ProjectFileInvitationFacts
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

from tests.factories import make_document, make_project

PACKS = Path(__file__).resolve().parents[6] / "packs"


@pytest.fixture(scope="module")
def templates() -> YamlTemplateRepository:
    repo = YamlTemplateRepository(PACKS)
    repo.load()
    return repo


class _Index:
    def __init__(self, project: Project | None) -> None:
        self._project = project

    def list_known(self) -> list[Path]:
        return []

    def register(self, folder: Path) -> None: ...

    def unregister(self, folder: Path) -> None: ...

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None:
        return (Path("/p"), self._project) if self._project is not None and self._project.id == project_id else None


def _coursework() -> Project:
    base = make_project(
        name="AI Assistant",
        documents=[
            make_document("project_proposal"),
            make_document("topic_application"),
            make_document("report"),
            replace(make_document("report--petrov"), def_id="report", owner="petrov"),
            make_document("presentation"),
        ],
    )
    return replace(
        base,
        lock=ProjectLock(pack_id="hse-cs-sse", template_id="coursework", version="2026.1.2", engine=EngineType.xelatex),
        authors=[Author(name="Алексей Шалаев", group="МСПИН261", email="a@hse.ru", slug="shalaev"), Author(name=" ")],
        meta={"name_ru": " Персональный ИИ-ассистент "},
        supervisor=Person(name="Хади Мухаммед", role=PersonRole.university),
        co_supervisor=Person(name="", role=PersonRole.company),
    )


async def test__facts__people_topic_kind_and_documents_in_project_order(templates: YamlTemplateRepository) -> None:
    project = _coursework()

    facts = await ProjectFileInvitationFacts(_Index(project), templates).facts(project.id, Lang.ru)

    assert facts is not None
    assert facts.project_name == "AI Assistant"
    assert facts.topic == "Персональный ИИ-ассистент"
    assert facts.work_kind == "Курсовой проект (магистратура, 1 курс)"
    assert facts.documents == (
        "Описание проекта и заявка на выполнение",
        "Заявление о выборе темы КП",
        "Отчёт о курсовом проекте",
        "Презентация",
    )
    assert facts.authors == (ProjectPerson(name="Алексей Шалаев", email="a@hse.ru", group="МСПИН261", slug="shalaev"),)
    assert dict(facts.supervisors) == {"supervisor": ProjectPerson(name="Хади Мухаммед")}


async def test__facts__english_names(templates: YamlTemplateRepository) -> None:
    project = _coursework()

    facts = await ProjectFileInvitationFacts(_Index(project), templates).facts(project.id, Lang.en)

    assert facts is not None
    assert facts.work_kind == "Course Project (MSc, 1st year)"
    assert facts.documents[-1] == "Presentation"


async def test__facts__unknown_template_gives_people_without_kind_and_documents(
    templates: YamlTemplateRepository,
) -> None:
    project = replace(
        _coursework(), lock=ProjectLock(pack_id="nope", template_id="x", version="1", engine=EngineType.xelatex)
    )

    facts = await ProjectFileInvitationFacts(_Index(project), templates).facts(project.id, Lang.ru)

    assert facts is not None
    assert (facts.work_kind, facts.documents) == (None, ())
    assert facts.supervisors["supervisor"].name == "Хади Мухаммед"


async def test__facts__missing_project_is_none(templates: YamlTemplateRepository) -> None:
    project = _coursework()

    assert await ProjectFileInvitationFacts(_Index(None), templates).facts(project.id, Lang.ru) is None
