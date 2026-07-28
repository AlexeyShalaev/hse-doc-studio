from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.enums import AIProviderType, EditFormat


@dataclass(frozen=True)
class SearchReplaceBlock:
    # One high-level edit: locate `search` in the file (exact or fuzzy) and swap
    # it for `replace`. Operates on the raw .tex text — LaTeX is never wrapped in JSON.
    search: str
    replace: str


# Strong, reliably-instructable providers get the efficient search/replace diff
# format; everything else (OpenAI-compatible endpoints and local Ollama models,
# whose tool/edit reliability varies) falls back to returning the whole file,
# which is a simpler contract that weak models follow more consistently.
_SEARCH_REPLACE_TYPES = frozenset({AIProviderType.claude, AIProviderType.openai})


def select_edit_format(provider_type: AIProviderType, model: str) -> EditFormat:  # noqa: ARG001 — model reserved for a future per-model allowlist
    return EditFormat.search_replace if provider_type in _SEARCH_REPLACE_TYPES else EditFormat.whole_file
