"""Проверка чужого `project.json` тем же разбором, что у загрузчика проекта."""

from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.infra.git_sync.remote_project_check import ProjectDocumentCheck
from hse_doc_studio.infra.persistence.serializers import serialize_project

from tests.factories import make_project

pytestmark = pytest.mark.unit


def _document() -> dict[str, Any]:
    return serialize_project(make_project())


def test__is_loadable__document_written_by_the_studio__accepted() -> None:
    assert ProjectDocumentCheck().is_loadable(_document())


@pytest.mark.parametrize(
    "change",
    [
        {"documents": "x"},
        {"authors": 5},
        {"meta": [1, 2]},
        {"created_at": "вчера"},
        {"name": None},
    ],
    ids=["documents", "authors", "meta", "created_at", "name"],
)
def test__is_loadable__garbage_in_a_field_the_loader_reads__rejected(change: dict[str, Any]) -> None:
    assert not ProjectDocumentCheck().is_loadable({**_document(), **change})
