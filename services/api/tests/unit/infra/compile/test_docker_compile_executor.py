from __future__ import annotations

import pytest
from hse_doc_studio.infra.compile.docker_compile_executor import _sum_texcount_total


def test__sum_texcount_total__three_field_total_line__sums_text_headers_captions() -> None:
    # texcount -1 prints "text+headers+captions (h/f/i/d) Total".
    assert _sum_texcount_total("21+3+0 (1/0/0/0) Total") == 24


def test__sum_texcount_total__noise_around_total_line__picks_the_count_line() -> None:
    block = "Some warning from texcount\n117+18+0 (1/0/0/0) Total\n"
    assert _sum_texcount_total(block) == 135


@pytest.mark.parametrize("block", ["", "no numbers here", "Total\n"])
def test__sum_texcount_total__unparseable_block__returns_none(block: str) -> None:
    assert _sum_texcount_total(block) is None
