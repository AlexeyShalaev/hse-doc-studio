"""Agent personas — preset instruction blocks that retune the assistant's voice
for a given stage of work.

A persona is chosen per chat session (``ChatSession.persona`` + ``persona_instructions``
for the free-form ``custom`` role) and applied by ``build_system_prompt`` /
``apply_persona``. For backward compatibility, when a session carries no persona,
the project-level default in ``project.meta["agent_persona"]`` is still honoured
(settable by the user or the agent's ``set_project_meta`` tool). ``default`` (or
absent/unknown) → no extra instruction.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.enums import Lang

META_KEY = "agent_persona"
DEFAULT_ID = "default"
CUSTOM_ID = "custom"

_Localized = dict[Lang, str]


@dataclass(frozen=True)
class PersonaInfo:
    """A selectable agent role, already resolved to one interface language.
    ``instruction`` is the system-prompt block; it is empty for the special
    ``default``/``custom`` roles (handled by ``persona_prompt``)."""

    id: str
    label: str
    description: str
    instruction: str = ""


@dataclass(frozen=True)
class _RawPersona:
    """Built-in role with its strings in every interface language. Built-in role
    labels/descriptions/instructions follow the INTERFACE language; user-defined
    custom roles are authored as-is and are not translated."""

    id: str
    label: _Localized
    description: _Localized
    instruction: _Localized | None = None


def _pick(loc: _Localized, language: Lang) -> str:
    return loc.get(language) or loc.get(Lang.ru) or ""


_RAW_PRESETS: tuple[_RawPersona, ...] = (
    _RawPersona(
        id="supervisor_critic",
        label={Lang.ru: "Научный руководитель-критик", Lang.en: "Critical research advisor"},
        description={
            Lang.ru: "Придирчиво оценивает логику, новизну и обоснованность выводов.",
            Lang.en: "Scrutinises the logic, novelty and soundness of conclusions.",
        },
        instruction={
            Lang.ru: (
                "Роль: научный руководитель-критик. Придирчиво оценивай логику, новизну, "
                "обоснованность выводов и соответствие цели/задачам; задавай неудобные вопросы "
                "и указывай на слабые места прямо, но конструктивно."
            ),
            Lang.en: (
                "Role: critical research advisor. Scrutinise the logic, novelty, soundness of "
                "conclusions and alignment with the stated goal/objectives; ask uncomfortable "
                "questions and point out weak spots directly but constructively."
            ),
        },
    ),
    _RawPersona(
        id="espd_proofreader",
        label={Lang.ru: "Корректор ЕСПД/ГОСТ", Lang.en: "ESPD/GOST proofreader"},
        description={
            Lang.ru: "Следит за оформлением по ГОСТ 7.32 и ЕСПД, нумерацией и ссылками.",
            Lang.en: "Watches GOST 7.32 / ESPD formatting, numbering and references.",
        },
        instruction={
            Lang.ru: (
                "Роль: корректор ЕСПД/ГОСТ. Следи за оформлением по ГОСТ 7.32 и ЕСПД, "
                "единообразием терминов и сокращений, нумерацией рисунков/таблиц/формул, "
                "оформлением списка литературы и ссылок. Предлагай точечные правки."
            ),
            Lang.en: (
                "Role: ESPD/GOST proofreader. Watch the formatting per GOST 7.32 and ESPD, "
                "consistency of terms and abbreviations, numbering of figures/tables/formulae, "
                "the bibliography and references. Suggest pinpoint fixes."
            ),
        },
    ),
    _RawPersona(
        id="latex_engineer",
        label={Lang.ru: "LaTeX-инженер", Lang.en: "LaTeX engineer"},
        description={
            Lang.ru: "Помогает с вёрсткой, макросами, окружениями и ошибками сборки.",
            Lang.en: "Helps with layout, macros, environments and build errors.",
        },
        instruction={
            Lang.ru: (
                "Роль: LaTeX-инженер. Помогай с вёрсткой, макросами, окружениями, ошибками "
                "сборки и преамбулой. Давай минимальные воспроизводимые правки .tex и проверяй "
                "сборку инструментами."
            ),
            Lang.en: (
                "Role: LaTeX engineer. Help with layout, macros, environments, build errors and "
                "the preamble. Provide minimal reproducible .tex edits and verify the build with "
                "tools."
            ),
        },
    ),
    _RawPersona(
        id="methodologist",
        label={Lang.ru: "Методист", Lang.en: "Methodologist"},
        description={
            Lang.ru: "Помогает со структурой, целью/задачами, новизной и связностью.",
            Lang.en: "Helps with structure, goal/objectives, novelty and coherence.",
        },
        instruction={
            Lang.ru: (
                "Роль: методист. Помогай со структурой работы, формулировками актуальности, "
                "цели, задач, объекта/предмета, научной новизны и практической значимости; "
                "следи за связностью введения и заключения."
            ),
            Lang.en: (
                "Role: methodologist. Help with the work's structure and the wording of "
                "relevance, goal, objectives, object/subject, scientific novelty and practical "
                "value; keep the introduction and conclusion coherent."
            ),
        },
    ),
    _RawPersona(
        id="committee_member",
        label={Lang.ru: "Член ГЭК (предзащита)", Lang.en: "Examination board member (pre-defence)"},
        description={
            Lang.ru: "Задаёт вопросы комиссии и помогает готовить доклад и ответы.",
            Lang.en: "Asks the board's questions and helps prepare the talk and answers.",
        },
        instruction={
            Lang.ru: (
                "Роль: член ГЭК на предзащите. Задавай вопросы, которые задаст комиссия, "
                "проверяй защищаемые тезисы на прочность и помогай готовить ответы и доклад."
            ),
            Lang.en: (
                "Role: examination board member at the pre-defence. Ask the questions the board "
                "will ask, stress-test the theses being defended, and help prepare the answers "
                "and the presentation."
            ),
        },
    ),
)

_RAW_DEFAULT = _RawPersona(
    id=DEFAULT_ID,
    label={Lang.ru: "Базовый", Lang.en: "Default"},
    description={
        Lang.ru: "Нейтральный ассистент без особой роли.",
        Lang.en: "A neutral assistant with no special role.",
    },
)
_RAW_CUSTOM = _RawPersona(
    id=CUSTOM_ID,
    label={Lang.ru: "Своя роль", Lang.en: "Custom role"},
    description={
        Lang.ru: "Опишите своими словами, каким должен быть агент.",
        Lang.en: "Describe in your own words what the agent should be.",
    },
)

_RAW_BY_ID: dict[str, _RawPersona] = {persona.id: persona for persona in _RAW_PRESETS}


def _to_info(raw: _RawPersona, language: Lang) -> PersonaInfo:
    return PersonaInfo(
        id=raw.id,
        label=_pick(raw.label, language),
        description=_pick(raw.description, language),
        instruction=_pick(raw.instruction, language) if raw.instruction else "",
    )


def persona_prompt(
    persona_id: str | None,
    custom_instructions: str | None = None,
    custom_personas: dict[str, str] | None = None,
    *,
    language: Lang = Lang.ru,
) -> str | None:
    """Return the instruction block for a persona, or None for the neutral default.

    Resolution order: ``default``/absent → None; ``custom`` → the trimmed
    free-form ``custom_instructions``; a built-in preset → its instruction in the
    given interface language; a user-defined role id → ``custom_personas[id]``
    (id→instruction map, authored as-is); unknown → None.
    """
    if not persona_id or persona_id == DEFAULT_ID:
        return None
    if persona_id == CUSTOM_ID:
        return (custom_instructions or "").strip() or None
    raw = _RAW_BY_ID.get(persona_id)
    if raw and raw.instruction:
        return _pick(raw.instruction, language)
    if custom_personas:
        block = custom_personas.get(persona_id)
        if block:
            return block.strip() or None
    return None


def apply_persona(
    base_prompt: str,
    persona_id: str | None,
    custom_instructions: str | None = None,
    custom_personas: dict[str, str] | None = None,
    *,
    language: Lang = Lang.ru,
) -> str:
    """Prepend nothing / append the persona block to any base system prompt."""
    block = persona_prompt(persona_id, custom_instructions, custom_personas, language=language)
    return f"{base_prompt}\n\n{block}" if block else base_prompt


def list_personas(language: Lang = Lang.ru) -> list[PersonaInfo]:
    """All selectable BUILT-IN roles (default + presets + custom) for UI listing / validation."""
    return [
        _to_info(_RAW_DEFAULT, language),
        *(_to_info(p, language) for p in _RAW_PRESETS),
        _to_info(_RAW_CUSTOM, language),
    ]


def builtin_duplicable_personas(language: Lang = Lang.ru) -> list[PersonaInfo]:
    """The shipped preset roles (with their instruction) — for the Settings UI to
    show read-only and duplicate into editable custom roles. Excludes the special
    default / inline-custom entries."""
    return [_to_info(p, language) for p in _RAW_PRESETS]
