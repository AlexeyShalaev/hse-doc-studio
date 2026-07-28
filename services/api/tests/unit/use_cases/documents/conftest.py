from __future__ import annotations

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.enums import EngineType

from tests.factories import make_document_definition


@pytest.fixture
def pres_definition() -> DocumentDefinition:
    pptx_variant = DocumentVariant(
        id="pptx",
        label={"ru": "PowerPoint"},
        source_file="pres/pptx/presentation.pptx",
        output_file="pres/pptx/presentation.pptx",
        output_name={"ru": "Презентация.pptx"},
        engine=None,
    )
    beamer_variant = DocumentVariant(
        id="beamer",
        label={"ru": "Beamer"},
        source_file="pres/beamer/pres.tex",
        output_file="pres/beamer/pres.pdf",
        output_name={"ru": "Презентация.pdf"},
        engine=EngineType.xelatex,
    )
    return make_document_definition("pres", required=False, variants=(pptx_variant, beamer_variant))
