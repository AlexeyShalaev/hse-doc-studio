"""Каталоги-владельцы определений документов (core.doc_dirs).

Bundle-раскладка: дерево пака == дереву проекта, пути манифеста уже в
проектном пространстве. Здесь проверяется вычисление каталогов определения
(сам док + варианты) и общего каталога-владельца для skip-логики
инстанциации (заменяет прежний core.path_remap, удалённый вместе с
kind-подпапками applied//research/).
"""

from __future__ import annotations

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.doc_dirs import def_dirs, def_source_dirs
from hse_doc_studio.core.enums import EngineType
from hse_doc_studio.core.value_objects import ChecksOverride
from pytest_lazy_fixtures import lf


def _doc(doc_id: str, source: str | None, output: str | None, variants: tuple = ()) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        name={"ru": doc_id},
        code={"ru": doc_id},
        source_file=source,
        output_file=output,
        output_name={"ru": f"{doc_id}.pdf"},
        gost_ref=None,
        required=True,
        checks=ChecksOverride(),
        variants=variants,
    )


def _variant(vid: str, source: str, output: str) -> DocumentVariant:
    return DocumentVariant(
        id=vid,
        label={"ru": vid},
        source_file=source,
        output_file=output,
        output_name={"ru": "Презентация"},
        engine=EngineType.xelatex if vid == "beamer" else None,
    )


@pytest.fixture
def plain_doc() -> DocumentDefinition:
    return _doc("thesis", "thesis/thesis.tex", "thesis/thesis.pdf")


@pytest.fixture
def variant_doc_same_dir() -> DocumentDefinition:
    # Вариантный док (ТЗ): оба варианта в ОДНОЙ папке документа.
    return _doc(
        "technical_specification",
        None,
        None,
        variants=(
            _variant(
                "espd",
                "technical_specification/technical_specification.tex",
                "technical_specification/technical_specification.pdf",
            ),
            _variant("srs-29148", "technical_specification/srs_29148.tex", "technical_specification/srs_29148.pdf"),
        ),
    )


@pytest.fixture
def presentation_doc() -> DocumentDefinition:
    # Презентация: варианты в подпапках presentation/<variant> — каталог-владелец
    # ОБЩИЙ РОДИТЕЛЬ `presentation` целиком (чтобы служебная presentation/assets
    # не «протекала» в базы, где презентации нет: shared в команде).
    return _doc(
        "presentation",
        None,
        None,
        variants=(
            _variant("pptx", "presentation/pptx/presentation.pptx", "presentation/pptx/presentation.pptx"),
            _variant("reveal", "presentation/reveal/index.html", "presentation/reveal/index.html"),
            _variant("beamer", "presentation/beamer/presentation.tex", "presentation/beamer/presentation.pdf"),
        ),
    )


@pytest.fixture
def sourceless_doc() -> DocumentDefinition:
    return _doc("empty", None, None)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("doc", "expected_def_dirs", "expected_source_dirs"),
    [
        pytest.param(lf("plain_doc"), {"thesis"}, {"thesis"}, id="plain_doc_owns_its_directory"),
        pytest.param(
            lf("variant_doc_same_dir"),
            {"technical_specification"},
            {"technical_specification"},
            id="variant_doc_collects_all_variant_dirs",
        ),
        pytest.param(
            lf("presentation_doc"),
            {"presentation/pptx", "presentation/reveal", "presentation/beamer"},
            {"presentation"},
            id="presentation_owner_is_common_parent",
        ),
        pytest.param(lf("sourceless_doc"), set(), set(), id="doc_without_sources_is_empty"),
    ],
)
def test__def_dirs_and_def_source_dirs__various_docs__returns_expected(
    doc: DocumentDefinition, expected_def_dirs: set[str], expected_source_dirs: set[str]
) -> None:
    assert def_dirs(doc) == expected_def_dirs
    assert def_source_dirs(doc) == expected_source_dirs
