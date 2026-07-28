from __future__ import annotations

import gzip

from hse_doc_studio.infra.synctex.parser import (
    load_synctex,
    normalize_input_path,
    parse_synctex,
)

# A minimal but well-formed SyncTeX v1 body: one page, a vbox high on the page
# (line 10) and an hbox near the top (line 12). Coordinates are in scaled points
# (sp); 4736286 sp ~= 72 pt and 4263256 sp ~= 64.8 pt at the default unit/mag.
SAMPLE = """SyncTeX Version:1
Input:1:./main.tex
Output:pdf
Magnification:1000
Unit:1
X Offset:0
Y Offset:0
Content:
{1
[1,10:4736286,42152922:30785863,41497600,0
(1,12:4736286,4263256:30785863,500000,100000
h1,12:4736286,4263256:30785863,500000,100000
)
]
}1
Postamble:
"""


def test__parse_synctex__well_formed_body__collects_inputs_and_boxes() -> None:
    doc = parse_synctex(SAMPLE.encode())
    assert doc.input_files == {1: "./main.tex"}
    assert 1 in doc.by_page
    assert {b.line for b in doc.by_page[1]} == {10, 12}


def test__inverse__click_near_hbox__returns_that_line() -> None:
    doc = parse_synctex(SAMPLE.encode())
    # Click near the line-12 hbox (~72pt, ~64pt from the top).
    hit = doc.inverse(page=1, x=72.0, y=64.0)
    assert hit is not None
    file, line, _column = hit
    assert line == 12
    assert file == "./main.tex"


def test__inverse__click_far_down_page__returns_vbox_line() -> None:
    doc = parse_synctex(SAMPLE.encode())
    # Far down the page (~640pt) -> the line-10 vbox.
    hit = doc.inverse(page=1, x=72.0, y=640.0)
    assert hit is not None
    assert hit[1] == 10


def test__forward__known_line__returns_boxes_with_page_and_position() -> None:
    doc = parse_synctex(SAMPLE.encode())
    boxes = doc.forward("main.tex", 12)
    assert boxes
    top = boxes[0]
    assert top.page == 1
    # ~72pt from left, width ~468pt — sanity bounds, not exact.
    assert 70 < top.h < 74
    assert 460 < top.width < 475


def test__forward__unknown_line__falls_back_to_nearest_on_same_page() -> None:
    doc = parse_synctex(SAMPLE.encode())
    # Line 999 doesn't exist; nearest fallback still yields something for the file.
    boxes = doc.forward("main.tex", 999)
    assert all(b.page == 1 for b in boxes)


def test__forward__project_relative_path__matches_by_basename() -> None:
    doc = parse_synctex(SAMPLE.encode())
    # Caller may pass a project-relative path; matching is by basename.
    assert doc.forward("sections/main.tex", 12)


def test__normalize_input_path__mount_prefix_and_dot__strips_to_relative_path() -> None:
    assert normalize_input_path("/work/sections/intro.tex") == "sections/intro.tex"
    assert normalize_input_path("./main.tex") == "main.tex"
    assert normalize_input_path("main.tex") == "main.tex"


def test__load_synctex__gzip_file_present__parses_document(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "main.synctex.gz"
    p.write_bytes(gzip.compress(SAMPLE.encode()))
    doc = load_synctex(p)
    assert doc is not None
    assert doc.inverse(page=1, x=72.0, y=64.0) is not None


def test__load_synctex__file_missing__returns_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert load_synctex(tmp_path / "nope.synctex.gz") is None
