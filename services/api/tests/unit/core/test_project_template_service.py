from __future__ import annotations

import pytest
from hse_doc_studio.core.catalog import (
    DocumentDefinition,
    DocumentVariant,
    PackInfo,
    TemplateInfo,
    TemplateVersion,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.value_objects import ChecksOverride
from pytest_lazy_fixtures import lf

from tests.factories import make_document_definition, make_template_version


class _MockTemplateRepo:
    def __init__(self, packs: list, versions: dict) -> None:
        self._packs = packs
        self._versions = versions

    def list_packs(self) -> list:
        return self._packs

    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion | None:
        return self._versions.get((pack_id, template_id, version))

    def list_versions(self, pack_id: str, template_id: str) -> list:
        return []


def _make_repo(
    pack_id: str = "p1",
    template_id: str = "tmpl",
    default_version: str = "1.0",
    has_version: bool = True,
) -> _MockTemplateRepo:
    version = make_template_version(pack_id, template_id, default_version)
    template_info = TemplateInfo(
        pack_id=pack_id,
        id=template_id,
        name={"ru": "Template"},
        short_name={"ru": "T"},
        description={"ru": ""},
        icon="icon",
        accent_hue=0,
        default_version=default_version,
    )
    pack_info = PackInfo(
        id=pack_id,
        name={"ru": "Pack"},
        description={"ru": ""},
        maintainer={"name": "Maintainer"},
        license="MIT",
        templates=(template_info,),
    )
    versions = {(pack_id, template_id, default_version): version} if has_version else {}
    return _MockTemplateRepo([pack_info], versions)


def _variant(vid: str, source: str, output: str) -> DocumentVariant:
    return DocumentVariant(
        id=vid,
        label={"ru": vid.upper()},
        source_file=source,
        output_file=output,
        output_name={"ru": f"{vid.upper()}.pdf"},
        engine=None,
    )


@pytest.fixture
def svc() -> ProjectTemplateService:
    return ProjectTemplateService()


@pytest.mark.unit
def test__project_template_service__pack_exists__returns_version(svc: ProjectTemplateService) -> None:
    repo = _make_repo()

    version = svc.get_default_version("p1", "tmpl", repo)

    assert version.version == "1.0"
    assert version.pack_id == "p1"


@pytest.mark.unit
def test__project_template_service__pack_missing__raises_not_found_error(svc: ProjectTemplateService) -> None:
    repo = _make_repo()

    with pytest.raises(NotFoundError, match="Пак не найден"):
        svc.get_default_version("nonexistent", "tmpl", repo)


@pytest.mark.unit
def test__project_template_service__template_missing__raises_not_found_error(svc: ProjectTemplateService) -> None:
    repo = _make_repo()

    with pytest.raises(NotFoundError, match="Шаблон не найден"):
        svc.get_default_version("p1", "nonexistent", repo)


@pytest.mark.unit
def test__project_template_service__version_missing__raises_not_found_error(svc: ProjectTemplateService) -> None:
    repo = _make_repo(has_version=False)

    with pytest.raises(NotFoundError, match="Версия по умолчанию"):
        svc.get_default_version("p1", "tmpl", repo)


@pytest.mark.unit
def test__project_template_service__no_variants__returns_source_and_output(svc: ProjectTemplateService) -> None:
    doc_def = make_document_definition("vkr")

    source, output = svc.resolve_document_source(doc_def, None)

    assert source == "vkr/main.tex"
    assert output == "vkr/main.pdf"


@pytest.mark.unit
def test__project_template_service__no_source_file_no_variants__raises_value_error(
    svc: ProjectTemplateService,
) -> None:
    doc_def = DocumentDefinition(
        id="vkr",
        name={"ru": "VKR"},
        code={"ru": "VKR"},
        source_file=None,
        output_file=None,
        output_name={"ru": "ВКР.pdf"},
        gost_ref=None,
        required=True,
        checks=ChecksOverride(),
        variants=(),
    )

    with pytest.raises(ValueError, match="нет source_file"):
        svc.resolve_document_source(doc_def, None)


@pytest.fixture
def two_variant_doc_def() -> DocumentDefinition:
    return make_document_definition(
        "vkr",
        variants=(
            _variant("a", "vkr/a.tex", "vkr/a.pdf"),
            _variant("b", "vkr/b.tex", "vkr/b.pdf"),
        ),
    )


@pytest.fixture
def one_variant_doc_def() -> DocumentDefinition:
    return make_document_definition("vkr", variants=(_variant("a", "vkr/a.tex", "vkr/a.pdf"),))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("doc_def", "chosen", "expected_source", "expected_output"),
    [
        pytest.param(lf("two_variant_doc_def"), None, "vkr/a.tex", "vkr/a.pdf", id="no_chosen_uses_first"),
        pytest.param(lf("two_variant_doc_def"), "b", "vkr/b.tex", "vkr/b.pdf", id="chosen_exists_uses_chosen"),
        pytest.param(
            lf("one_variant_doc_def"),
            "nonexistent",
            "vkr/a.tex",
            "vkr/a.pdf",
            id="chosen_missing_falls_back_to_first",
        ),
    ],
)
def test__resolve_document_source__variants__returns_expected(
    svc: ProjectTemplateService,
    doc_def: DocumentDefinition,
    chosen: str | None,
    expected_source: str,
    expected_output: str,
) -> None:
    source, output = svc.resolve_document_source(doc_def, chosen)

    assert source == expected_source
    assert output == expected_output
