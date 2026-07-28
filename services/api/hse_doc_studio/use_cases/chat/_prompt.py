from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentMessage, ToolCall
from hse_doc_studio.core.entities import ChatMessage, Project
from hse_doc_studio.core.enums import ChatContentKind, ChatMessageRole, EditFormat, Lang
from hse_doc_studio.use_cases.chat.personas import META_KEY, persona_prompt

# The interface (conversation) language is independent from the document's
# working language (`project.lang`): the agent replies in the interface language
# while editing a document that may be authored in another language.
#
# Ни вуз, ни образовательную программу в промпте не называем: и то и другое задаёт пак
# шаблонов проекта (id пака = вуз + факультет + ОП), а паков может быть несколько — в том
# числе под другой вуз. Зашитая конкретика стала бы для остальных паков ложным фактом,
# который модель приняла бы за истину. Имя продукта отсылает к НИУ ВШЭ, приложение — нет.
_BASE_PROMPT: dict[Lang, str] = {
    Lang.ru: (
        "Ты — ИИ-ассистент внутри локального инструмента подготовки учебных документов. "
        "Документы пишутся на LaTeX и должны соответствовать требованиям пака шаблонов, "
        "выбранного в проекте (ГОСТ/ЕСПД и методические указания вуза). Помогай писать и "
        "править .tex, разбирать ошибки сборки и замечания проверок, трассировать "
        "требования и собирать комплект.\n"
        "Правила: отвечай по-русски (независимо от языка самого документа); опирайся на "
        "инструменты, а не на догадки (читай файлы, смотри замечания); прежде чем менять "
        "текст, изучи контекст; будь точным и кратким. Если не хватает информации для "
        "уверенного действия (какой документ/профиль/вариант выбрать), не угадывай — задай "
        "уточняющий вопрос инструментом ask_user с вариантами ответа и дождись выбора."
    ),
    Lang.en: (
        "You are the AI assistant inside a local tool for preparing academic documents. "
        "Documents are written in LaTeX and must comply with the requirements of the "
        "template pack selected in the project (GOST/ESPD standards and the university's "
        "own guidelines). Help write and edit .tex files, work through build errors and "
        "check findings, trace requirements and assemble the submission package.\n"
        "Rules: reply in English (regardless of the document's own language); rely on tools "
        "rather than guesswork (read files, look at findings); study the context before "
        "changing text; be precise and concise. If you lack the information to act confidently "
        "(which document/profile/variant to choose), don't guess — ask a clarifying question "
        "with the ask_user tool, offering options, and wait for the choice."
    ),
}

_EDIT_FORMAT_HINT: dict[Lang, dict[EditFormat, str]] = {
    Lang.ru: {
        EditFormat.search_replace: (
            "Для правок .tex используй точные блоки поиска-замены по исходному тексту (не оборачивай LaTeX в JSON)."
        ),
        EditFormat.whole_file: "Для правок .tex возвращай полный обновлённый текст файла.",
    },
    Lang.en: {
        EditFormat.search_replace: (
            "For .tex edits use exact search-replace blocks against the source text (do not wrap LaTeX in JSON)."
        ),
        EditFormat.whole_file: "For .tex edits return the full updated file text.",
    },
}


def _project_line(project: Project, language: Lang) -> str:
    if language == Lang.en:
        return (
            f"Project: template «{project.lock.template_id}» (pack {project.lock.pack_id}, "
            f"version {project.lock.version}), working language: {project.lang}."
        )
    return (
        f"Проект: шаблон «{project.lock.template_id}» (пакет {project.lock.pack_id}, "
        f"версия {project.lock.version}), язык работы: {project.lang}."
    )


def _team_line(project: Project, language: Lang) -> str | None:
    """Командный контекст: раскладка по авторам, темы, системное название.

    Solo-проекту строка не нужна — агент работает с плоской раскладкой.
    """
    if str(project.staffing) != "team":
        return None
    members: list[str] = []
    # Черновики из настроек (пустое имя) агенту не показываем.
    for author in project.authors:
        if not author.name.strip():
            continue
        if language == Lang.en:
            topic = f" — topic: “{author.topic}”" if author.topic else ""
            managed = "" if author.managed else " (set not managed here)"
        else:
            topic = f" — тема: «{author.topic}»" if author.topic else ""
            managed = "" if author.managed else " (комплект не ведётся здесь)"
        members.append(f"{author.name} [папка {author.slug or '?'}]{topic}{managed}")
    joined = "; ".join(members)
    if language == Lang.en:
        return (
            f"TEAM project: system name «{project.name}». Layout: shared documents live in shared/, "
            f"each author's personal set in the folder named by their slug; personal doc ids look "
            f"like 'vkr--<slug>'. Authors: {joined}."
        )
    return (
        f"КОМАНДНЫЙ проект: название системы «{project.name}». Раскладка: общие документы в shared/, "
        f"личный комплект каждого автора — в папке с его слагом; id личных документов вида "
        f"'vkr--<слаг>'. Авторы: {joined}."
    )


def _doc_link_hint(doc_ids: list[str], language: Lang) -> str:
    joined = ", ".join(doc_ids)
    if language == Lang.en:
        return (
            "When you mention a document from the package, format it as a link "
            "[Text](doc:<doc_id>), e.g. [VKR](doc:vkr) — the interface turns it into a jump "
            "to the document. Use only documents that exist in the project: " + joined + "."
        )
    return (
        "Когда упоминаешь документ комплекта, оформляй его ссылкой в формате "
        "[Текст](doc:<doc_id>), например [ВКР](doc:vkr) — интерфейс превратит её в "
        "переход к документу. Используй только существующие документы проекта: " + joined + "."
    )


def build_system_prompt(
    project: Project,
    edit_format: EditFormat,
    rules: str | None,
    *,
    persona_id: str | None = None,
    persona_instructions: str | None = None,
    custom_personas: dict[str, str] | None = None,
    language: Lang = Lang.ru,
) -> str:
    parts = [_BASE_PROMPT[language]]
    # The persona retunes the voice for the current stage. An explicit per-session
    # persona wins; when unset (None), fall back to the project-level default in
    # project.meta["agent_persona"]. "default"/unknown → neutral base behaviour.
    # `custom_personas` (id→instruction) resolves user-defined roles.
    if persona_id is None:
        meta_persona = project.meta.get(META_KEY)
        persona = persona_prompt(
            meta_persona if isinstance(meta_persona, str) else None, None, custom_personas, language=language
        )
    else:
        persona = persona_prompt(persona_id, persona_instructions, custom_personas, language=language)
    if persona:
        parts.append(persona)
    parts.append(_project_line(project, language))
    team_line = _team_line(project, language)
    if team_line:
        parts.append(team_line)
    parts.append(_EDIT_FORMAT_HINT[language][edit_format])
    doc_ids = [doc.id for doc in project.documents]
    if doc_ids:
        parts.append(_doc_link_hint(doc_ids, language))
    if rules:
        label = "Project rules:" if language == Lang.en else "Правила проекта:"
        parts.append(f"{label}\n" + rules.strip())
    return "\n\n".join(parts)


def _text_of(message: ChatMessage) -> str:
    return "\n".join(b.text for b in message.blocks if b.kind == ChatContentKind.text and b.text)


def chat_history_to_agent_messages(messages: list[ChatMessage]) -> list[AgentMessage]:
    """Project the persisted transcript into the provider-neutral message list.

    A summary message becomes a system message (compaction, Phase 5); each tool
    message expands to one AgentMessage per tool_result block.
    """
    out: list[AgentMessage] = []
    for message in messages:
        if message.role == ChatMessageRole.user:
            out.append(AgentMessage(role="user", content=_text_of(message)))
        elif message.role == ChatMessageRole.assistant:
            tool_calls = tuple(
                ToolCall(id=b.call_id or "", name=b.tool_name or "", arguments=b.args)
                for b in message.blocks
                if b.kind == ChatContentKind.tool_call
            )
            out.append(AgentMessage(role="assistant", content=_text_of(message), tool_calls=tool_calls))
        elif message.role == ChatMessageRole.tool:
            out.extend(
                AgentMessage(role="tool", content=b.result or "", tool_call_id=b.call_id, name=b.tool_name)
                for b in message.blocks
                if b.kind == ChatContentKind.tool_result
            )
        elif message.role == ChatMessageRole.summary:
            out.append(AgentMessage(role="system", content=_text_of(message)))
    return out
