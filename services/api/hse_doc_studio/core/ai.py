from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.entities import AIProvider, ChatMessage, ChatSummaryBlock


class IAIModelLister(Protocol):
    # Live-lists the models a provider exposes (calls the provider's /models
    # endpoint under the hood). Defined in core so use cases can depend on it
    # without importing infra — the SDK-backed implementation lives in
    # infra/ai. Doubles as a connection/credentials check: a successful listing
    # means the key + base_url are valid.
    async def list_models(self, provider: AIProvider) -> list[str]: ...


class IChatSummarizer(Protocol):
    # Condenses a span of older transcript messages into a single rolling
    # summary (an LLM call under the hood, via the agent provider). Defined in
    # core so the compaction service/use case can depend on it without importing
    # infra; the implementation lives in infra/ai/agent. `prior_summary` is the
    # previous rolling summary to fold in so summaries stay bounded.
    async def summarize(
        self,
        messages: list[ChatMessage],
        prior_summary: ChatSummaryBlock | None,
        model: str,
        provider: AIProvider,
    ) -> str: ...
