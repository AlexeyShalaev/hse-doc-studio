from __future__ import annotations

import pytest
from hse_doc_studio.core.vcs.build_pdf import is_build_output_pdf, is_pdf_outside_history

_FILES = {"vkr/vkr.tex", "vkr/images/scheme.png", "task/task.docx", "slides/talk.pptx"}


def _is_file(path: str) -> bool:
    return path in _FILES


@pytest.mark.parametrize(
    ("path", "built"),
    [
        ("vkr/vkr.pdf", True),
        ("task/task.pdf", True),
        ("slides/talk.pdf", True),
        ("vkr/images/scheme.pdf", False),
        ("vkr/images/figure.pdf", False),
        ("appendix/scan.pdf", False),
        ("vkr/vkr.tex", False),
        ("vkr/vkr.local.pdf", True),
        ("vkr/vkr.local2.pdf", True),
        ("vkr/images/figure.local.pdf", False),
    ],
)
def test__is_build_output_pdf__only_pdf_next_to_a_same_named_source(path: str, built: bool) -> None:
    assert is_build_output_pdf(path, _is_file) is built


def test__is_pdf_outside_history__service_pdfs_stay_out_user_pdfs_go_in() -> None:
    assert is_pdf_outside_history(".hse-studio/frozen/vkr.pdf", _is_file)
    assert is_pdf_outside_history("vkr/vkr.pdf", _is_file)
    assert not is_pdf_outside_history("vkr/images/figure.pdf", _is_file)
    assert not is_pdf_outside_history("vkr/images/scheme.png", _is_file)
