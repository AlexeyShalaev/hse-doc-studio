from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
DESIGN_DIR = ROOT / "docs" / "design"
_MD_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)#\s]+)")
_CODE_PATH = re.compile(r"`((?:docs/design|\.claude/(?:rules|skills))/[\w./-]+)`")


def _docs() -> list[Path]:
    return sorted([*DESIGN_DIR.glob("*.md"), *(ROOT / ".claude" / "rules").glob("backend-*.md")])


@pytest.mark.parametrize("doc", _docs(), ids=lambda p: p.name)
def test__design_docs__links_and_paths__exist(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    missing = [m for m in _CODE_PATH.findall(text) if not (ROOT / m).exists()]
    missing += [m for m in _MD_LINK.findall(text) if not (doc.parent / m).exists()]
    assert not missing, f"{doc.name}: битые ссылки {missing}"


def test__design_docs__fenced_blocks__balanced() -> None:
    for doc in _docs():
        fences = [ln for ln in doc.read_text(encoding="utf-8").splitlines() if ln.lstrip().startswith("```")]
        assert len(fences) % 2 == 0, f"{doc.name}: незакрытый блок кода"
