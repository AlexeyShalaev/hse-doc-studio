"""Где цитата треда в живом тексте файла: то же разрешение, что у клиента (`web-app/.../review/lib/anchor.ts`).

Нужно серверу для меток в превью PDF: от найденного фрагмента берётся строка для прямого SyncTeX.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hse_doc_studio.core.review.entities import Anchor

_CONTEXT = 40
_MAX_CANDIDATES = 200
_EDITED_WINDOW_FACTOR = 3
_EDITED_WINDOW_SLACK = 60
_PROBE = 16

AnchorState = Literal["ok", "moved", "edited"]


@dataclass(frozen=True)
class ResolvedAnchor:
    state: AnchorState
    start: int
    end: int


def _common_suffix(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[len(a) - 1 - n] == b[len(b) - 1 - n]:
        n += 1
    return n


def _common_prefix(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


def _context_score(text: str, at: int, anchor: Anchor) -> int:
    before = text[max(0, at - _CONTEXT * 2) : at]
    after = text[at + len(anchor.quote) : at + len(anchor.quote) + _CONTEXT * 2]
    return _common_suffix(before, anchor.prefix) + _common_prefix(after, anchor.suffix)


def _by_quote(text: str, anchor: Anchor) -> ResolvedAnchor | None:
    candidates: list[int] = []
    at = text.find(anchor.quote)
    while at != -1 and len(candidates) < _MAX_CANDIDATES:
        candidates.append(at)
        at = text.find(anchor.quote, at + 1)
    if not candidates:
        return None
    best = max(candidates, key=lambda c: (_context_score(text, c, anchor), -abs(c - anchor.start)))
    return ResolvedAnchor("ok" if best == anchor.start else "moved", best, best + len(anchor.quote))


def _by_context(text: str, anchor: Anchor) -> ResolvedAnchor | None:
    before = anchor.prefix[-_PROBE:]
    after = anchor.suffix[:_PROBE]
    if not before and not after:
        return None
    if before:
        near = text.rfind(before, 0, max(0, anchor.start) + len(before))
        at = near if near != -1 else text.find(before)
        if at == -1:
            return None
        start = at + len(before)
    else:
        start = 0
    window = len(anchor.quote) * _EDITED_WINDOW_FACTOR + _EDITED_WINDOW_SLACK
    if after:
        at = text.find(after, start)
        if at == -1 or at - start > window:
            return None
        end = at
    else:
        end = len(text)
    return ResolvedAnchor("edited", start, end) if end > start else None


def resolve_anchor(text: str, anchor: Anchor) -> ResolvedAnchor | None:
    """Фрагмент цитаты в тексте или None, если он удалён или переписан."""
    if not anchor.quote:
        return None
    if text[anchor.start : anchor.end] == anchor.quote and _context_score(text, anchor.start, anchor) == len(
        anchor.prefix
    ) + len(anchor.suffix):
        return ResolvedAnchor("ok", anchor.start, anchor.end)
    return _by_quote(text, anchor) or _by_context(text, anchor)


def make_anchor(text: str, start: int, end: int) -> Anchor:
    """Цитата `[start, end)` с контекстом, как `makeAnchor` клиента."""
    return Anchor(
        quote=text[start:end],
        prefix=text[max(0, start - _CONTEXT) : start],
        suffix=text[end : end + _CONTEXT],
        start=start,
        end=end,
    )
