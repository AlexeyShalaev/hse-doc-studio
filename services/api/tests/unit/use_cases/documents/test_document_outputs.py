"""Куда документ выпускает результат: вариант пака, свой загруженный файл, документ без определения."""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.use_cases.documents.document_outputs import DocumentOutputs

from tests.factories import (
    make_custom_file_override,
    make_document,
    make_document_definition,
    make_project,
    make_template_version,
)


class _Templates:
    def __init__(self, version: TemplateVersion | None) -> None:
        self.version = version

    def get_version(self, _pack: str, _template: str, _version: str) -> TemplateVersion | None:
        return self.version


def _project(*documents: object) -> Project:
    project = make_project(documents=list(documents))  # type: ignore[arg-type]
    return replace(project, lock=replace(project.lock, version="1.0"))


def test__variants_custom_files_and_unknown_documents(pres_definition: DocumentDefinition) -> None:
    version = make_template_version(documents=(make_document_definition("tz"), pres_definition))
    project = _project(
        make_document("tz"),
        make_document("pres", chosen_variant="pptx"),
        make_document("custom", custom_file=make_custom_file_override(stored_path="custom/_custom/a.docx")),
        make_document("gone"),
    )

    found = DocumentOutputs(_Templates(version)).of(project)  # type: ignore[arg-type]

    assert found == {
        "tz": "tz/main.pdf",
        "pres": "pres/pptx/presentation.pptx",
        "custom": "custom/_custom/a.docx",
        "gone": None,
    }


def test__beamer_variant_is_a_pdf(pres_definition: DocumentDefinition) -> None:
    version = make_template_version(documents=(pres_definition,))

    found = DocumentOutputs(_Templates(version)).of(_project(make_document("pres", chosen_variant="beamer")))  # type: ignore[arg-type]

    assert found == {"pres": "pres/beamer/pres.pdf"}


def test__pack_version_not_installed__only_custom_files_are_known() -> None:
    project = _project(make_document("tz"), make_document("c", custom_file=make_custom_file_override()))

    assert DocumentOutputs(_Templates(None)).of(project) == {"tz": None, "c": "tz/_custom/file.docx"}  # type: ignore[arg-type]
