"""Карточка проекта в списке сервера: владелец и роль человека, пути папки нет."""

from __future__ import annotations

from uuid import uuid4

from hse_doc_studio.api.routers.v1.projects import _map_project_summary
from hse_doc_studio.api.schemas.session import ProjectSummary
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import ProjectMembership, ProjectOwnerView

from tests.factories import make_project


def test__map_project_summary__owner_and_role_without_folder() -> None:
    project = make_project()
    owner = ProjectOwnerView(kind="user", id="user-a", name="Алиса", slug=None)

    summary = _map_project_summary(project, ProjectMembership(project.id, owner, Role.reviewer))

    assert ProjectSummary.model_validate(summary.model_dump(mode="json")) == summary
    assert (summary.my_role, summary.owner.name, summary.id) == ("reviewer", "Алиса", str(project.id))
    assert "folder" not in summary.model_dump()


def test__map_project_summary__org_owner() -> None:
    project = make_project()
    owner = ProjectOwnerView(kind="org", id=str(uuid4()), name="Кафедра", slug="kafedra")

    summary = _map_project_summary(project, ProjectMembership(project.id, owner, Role.owner))

    assert (summary.owner.kind, summary.owner.slug) == ("org", "kafedra")
