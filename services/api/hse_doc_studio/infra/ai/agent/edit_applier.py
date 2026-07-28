from __future__ import annotations

import difflib
from collections.abc import Sequence

from hse_doc_studio.core.agent.edits import SearchReplaceBlock
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language

# Above this line-window similarity a fuzzy match is accepted; tuned so minor
# model drift (whitespace, a changed word) still lands while unrelated text does not.
_DEFAULT_THRESHOLD = 0.9


class FuzzySearchReplaceApplier:
    """Apply high-level search/replace blocks to file text, exact-then-fuzzy.

    Atomic: if ANY block fails to locate its target, nothing is written and the
    errors (with the nearest snippet) are returned, so a mis-generated block can
    never corrupt the file — the agent retries with a corrected block.
    """

    def __init__(self, threshold: float = _DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    def apply(self, content: str, blocks: Sequence[SearchReplaceBlock]) -> tuple[str, list[str]]:
        working = content
        errors: list[str] = []
        for index, block in enumerate(blocks, start=1):
            replaced, ok, near = self._apply_one(working, block)
            if ok:
                working = replaced
            else:
                en = current_interface_language() is Lang.en
                if near:
                    snippet = near.strip()[:80]
                    hint = f" Nearest fragment: «{snippet}…»" if en else f" Ближайший фрагмент: «{snippet}…»"
                else:
                    hint = ""
                msg = (
                    f"block #{index}: text to replace not found.{hint}"
                    if en
                    else f"блок #{index}: не найден текст для замены.{hint}"
                )
                errors.append(msg)
        if errors:
            return content, errors  # atomic — no partial writes
        return working, []

    def _apply_one(self, content: str, block: SearchReplaceBlock) -> tuple[str, bool, str]:
        if not block.search:
            return content, False, ""
        idx = content.find(block.search)
        if idx != -1:
            return content[:idx] + block.replace + content[idx + len(block.search) :], True, ""
        ratio, start, end, window = self._best_window(content, block.search)
        if ratio >= self._threshold:
            return content[:start] + block.replace + content[end:], True, ""
        return content, False, window

    def _best_window(self, content: str, search: str) -> tuple[float, int, int, str]:
        lines = content.splitlines(keepends=True)
        span = max(1, len(search.splitlines()))
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        matcher = difflib.SequenceMatcher(autojunk=False)
        matcher.set_seq2(search.strip())
        best_ratio = 0.0
        best_start = 0
        best_end = 0
        best_text = ""
        for i in range(len(lines) - span + 1):
            window_text = "".join(lines[i : i + span])
            matcher.set_seq1(window_text.strip())
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = offsets[i]
                best_end = offsets[i + span]
                best_text = window_text
        return best_ratio, best_start, best_end, best_text
