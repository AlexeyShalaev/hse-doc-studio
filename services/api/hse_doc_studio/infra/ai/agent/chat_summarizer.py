from __future__ import annotations

import asyncio

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.entities import AgentMessage
from hse_doc_studio.core.agent.protocols import IAgentProvider
from hse_doc_studio.core.entities import AIProvider, ChatMessage, ChatSummaryBlock
from hse_doc_studio.core.enums import ChatContentKind, Lang
from hse_doc_studio.core.i18n import current_interface_language

_SYSTEM: dict[Lang, str] = {
    Lang.ru: (
        "Ты сжимаешь историю диалога ИИ-ассистента по подготовке LaTeX-документов. "
        "Сохрани факты, важные для продолжения работы: что просил пользователь, какие "
        "файлы и требования затрагивались, какие правки/сборки/замечания уже сделаны и "
        "их результат, открытые задачи. Пиши кратко, по-русски, без воды."
    ),
    Lang.en: (
        "You compress the conversation history of an AI assistant that helps prepare LaTeX "
        "documents. Keep the facts that matter for continuing the work: what the user asked, "
        "which files and requirements were touched, which edits/builds/findings were already "
        "done and their result, open tasks. Write briefly, in English, no fluff."
    ),
}

_PRIOR_SUMMARY_LABEL: dict[Lang, str] = {
    Lang.ru: "Предыдущее краткое содержание:\n",
    Lang.en: "Previous summary:\n",
}
_MESSAGES_LABEL: dict[Lang, str] = {
    Lang.ru: "Сообщения для сжатия:\n",
    Lang.en: "Messages to compress:\n",
}


class SdkChatSummarizer:
    """IChatSummarizer backed by the agent provider (one tool-free model call)."""

    def __init__(self, provider: IAgentProvider) -> None:
        self._provider = provider

    async def summarize(
        self,
        messages: list[ChatMessage],
        prior_summary: ChatSummaryBlock | None,
        model: str,
        provider: AIProvider,
    ) -> str:
        language = current_interface_language()
        parts: list[str] = []
        if prior_summary is not None:
            parts.append(_PRIOR_SUMMARY_LABEL[language] + prior_summary.text)
        parts.append(_MESSAGES_LABEL[language] + "\n".join(_render(m) for m in messages))
        turn = await self._provider.run_turn(
            provider=provider,
            model=model,
            messages=[AgentMessage(role="user", content="\n\n".join(parts))],
            tools=[],
            system=_SYSTEM[language],
            tool_choice_allowed=False,
            max_output_tokens=settings.agent.summary_max_tokens,
            temperature=0.2,
            sink=None,
            cancel=asyncio.Event(),
        )
        return turn.text.strip()


def _render(message: ChatMessage) -> str:
    en = current_interface_language() is Lang.en
    call_label = "call" if en else "вызов"
    result_label = "result" if en else "результат"
    chunks: list[str] = []
    for block in message.blocks:
        if block.kind == ChatContentKind.text and block.text:
            chunks.append(block.text)
        elif block.kind == ChatContentKind.tool_call:
            chunks.append(f"[{call_label} {block.tool_name}({block.args})]")
        elif block.kind == ChatContentKind.tool_result and block.result:
            chunks.append(f"[{result_label} {block.tool_name}: {block.result[:300]}]")
    return f"{message.role.value}: {' '.join(chunks)}"
