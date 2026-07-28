"""Pure-Python SyncTeX parser for two-way PDF <-> source navigation.

`latexmk -synctex=1` drops a ``<stem>.synctex.gz`` next to the PDF. It records,
for every typeset box/glyph, the source file + line it came from and where it
landed on the page. We parse that once (cached by mtime) and answer two queries:

* **inverse** (PDF -> source): given a click at page + (x, y) in PDF points from
  the top-left, return the nearest record's ``(file, line, column)``.
* **forward** (source -> PDF): given ``(file basename, line)``, return the boxes
  that line produced, in PDF points from the top-left, so the viewer can scroll
  there and flash a highlight.

Coordinates are converted from SyncTeX "scaled points" to PDF points (big
points, 1/72 in) with the standard ``sp / 65781.76`` factor (65536 sp per TeX pt
times 72/72.27 pt-per-bp), honouring the file's unit / magnification / offsets.
SyncTeX's vertical axis already runs top-down from the page top, matching pdf.js.
"""

from __future__ import annotations

import gzip
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()

# sp -> PDF big-point: 65536 sp per TeX pt, and 72/72.27 pt per bp.
_SP_PER_BP = 65536.0 * 72.27 / 72.0  # == 65781.76

# A content record: a type char, then `tag,line[,column]:H,V[:W,Height,Depth]`.
_RECORD_RE = re.compile(
    r"^(?P<type>[\[\(hvxkg\$])(?P<tag>\d+),(?P<line>\d+)(?:,(?P<col>\d+))?"
    r":(?P<h>-?\d+),(?P<v>-?\d+)"
    r"(?::(?P<w>-?\d+),(?P<height>-?\d+),(?P<depth>-?\d+))?"
)


@dataclass(slots=True)
class SyncBox:
    page: int
    tag: int
    line: int
    column: int
    # All in PDF points from the page's top-left.
    h: float
    v: float
    width: float
    height: float
    depth: float


@dataclass(slots=True)
class SyncTexDocument:
    input_files: dict[int, str] = field(default_factory=dict)
    by_page: dict[int, list[SyncBox]] = field(default_factory=dict)
    by_line: dict[int, list[SyncBox]] = field(default_factory=dict)

    # ── queries ──────────────────────────────────────────────────────────────
    def inverse(self, page: int, x: float, y: float) -> tuple[str, int, int] | None:
        """PDF point (x, y) on `page` -> (file, line, column) of the nearest box."""
        candidates = self.by_page.get(page)
        if not candidates:
            return None
        best: SyncBox | None = None
        best_key = (float("inf"), float("inf"), float("inf"))
        for box in candidates:
            top = box.v - box.height
            bottom = box.v + box.depth
            dv = 0.0 if top <= y <= bottom else min(abs(y - top), abs(y - bottom))
            right = box.h + box.width
            dh = 0.0 if box.h <= x <= right else min(abs(x - box.h), abs(x - right))
            # Vertical proximity dominates (lines stack vertically); ties break to
            # the tightest box so an enclosing page-tall vbox loses to the line's
            # own hbox/glyph record that actually carries the source position.
            key = (dv, dh, box.height + box.depth)
            if key < best_key:
                best_key = key
                best = box
        if best is None:
            return None
        return (self.input_files.get(best.tag, ""), best.line, best.column)

    def forward(self, file_basename: str, line: int) -> list[SyncBox]:  # noqa: C901
        """(file basename, line) -> boxes it produced (topmost first)."""
        target = _basename(file_basename)
        exact = [
            box
            for box in self.by_line.get(line, ())  # exact line first
            if _basename(self.input_files.get(box.tag, "")) == target
        ]
        if exact:
            return _ordered(exact)
        # Fall back to the closest line that produced output in this file (a line
        # may be empty / a comment / inside a macro and emit nothing itself).
        nearest_line: int | None = None
        for cand_line, boxes in self.by_line.items():
            if not any(_basename(self.input_files.get(b.tag, "")) == target for b in boxes):
                continue
            if nearest_line is None or abs(cand_line - line) < abs(nearest_line - line):
                nearest_line = cand_line
        if nearest_line is None:
            return []
        near = [b for b in self.by_line.get(nearest_line, ()) if _basename(self.input_files.get(b.tag, "")) == target]
        return _ordered(near)


def _ordered(boxes: list[SyncBox]) -> list[SyncBox]:
    # Topmost (then leftmost) first — that's where the viewer should jump.
    return sorted(boxes, key=lambda b: (b.page, b.v - b.height, b.h))


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def normalize_input_path(path: str) -> str:
    """Best-effort project-relative path: drop the container mount + ``./``."""
    p = path.strip().replace("\\", "/")
    for prefix in ("/work/", "./"):
        if p.startswith(prefix):
            p = p[len(prefix) :]
    return p


def _record_from_match(m: re.Match[str], page: int, k: float, off_x: float, off_y: float) -> SyncBox:
    w_raw = m.group("w")
    h_raw = m.group("height")
    d_raw = m.group("depth")
    return SyncBox(
        page=page,
        tag=int(m.group("tag")),
        line=int(m.group("line")),
        column=int(m.group("col") or 0),
        h=int(m.group("h")) * k + off_x,
        v=int(m.group("v")) * k + off_y,
        width=int(w_raw) * k if w_raw is not None else 0.0,
        height=int(h_raw) * k if h_raw is not None else 0.0,
        depth=int(d_raw) * k if d_raw is not None else 0.0,
    )


def parse_synctex(raw: bytes) -> SyncTexDocument:  # noqa: C901, PLR0912, PLR0915
    """Parse raw ``.synctex`` / ``.synctex.gz`` bytes into a queryable document."""
    if raw[:2] == b"\x1f\x8b":  # gzip magic
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:  # truncated / corrupt archive
            logger.warning("synctex: gunzip failed", exc=str(exc))
            return SyncTexDocument()
    text = raw.decode("utf-8", errors="replace")

    doc = SyncTexDocument()
    unit = 1.0
    mag = 1000.0
    x_off = 0.0
    y_off = 0.0
    in_content = False
    page = 0

    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("Input:"):
            # Maps a tag number to the source file path it came from.
            rest = line[len("Input:") :]
            tag_str, sep, path = rest.partition(":")
            if sep and tag_str.isdigit():
                doc.input_files[int(tag_str)] = path
            continue
        if not in_content:
            if line.startswith("Content:"):
                in_content = True
            elif line.startswith("Magnification:"):
                mag = _num(line, mag)
            elif line.startswith("Unit:"):
                unit = _num(line, unit)
            elif line.startswith("X Offset:"):
                x_off = _num(line, x_off)
            elif line.startswith("Y Offset:"):
                y_off = _num(line, y_off)
            continue

        head = line[0]
        if head in ("{", "<"):  # sheet / vbox-on-page start
            tail = line[1:].strip()
            if tail.isdigit():
                page = int(tail)
            continue
        if head in "}>])":  # sheet end / box close — no coordinates
            continue
        if head == "P" and line.startswith("Postamble"):
            break

        m = _RECORD_RE.match(line)
        if m is None or page <= 0:
            continue
        k = unit * (mag / 1000.0) / _SP_PER_BP
        box = _record_from_match(m, page, k, x_off / _SP_PER_BP, y_off / _SP_PER_BP)
        doc.by_page.setdefault(page, []).append(box)
        doc.by_line.setdefault(box.line, []).append(box)

    return doc


def _num(line: str, default: float) -> float:
    try:
        return float(line.split(":", 1)[1].strip())
    except (ValueError, IndexError):
        return default


# ── mtime-keyed cache so repeated clicks don't re-parse a big file ────────────
_CACHE: OrderedDict[tuple[str, int], SyncTexDocument] = OrderedDict()
_CACHE_MAX = 8


def load_synctex(path: Path) -> SyncTexDocument | None:
    """Load + parse `path`, cached by (path, mtime). None if the file is absent."""
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    key = (str(path), mtime)
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    try:
        raw = path.read_bytes()
    except OSError as exc:
        logger.warning("synctex: read failed", path=str(path), exc=str(exc))
        return None
    doc = parse_synctex(raw)
    _CACHE[key] = doc
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return doc
