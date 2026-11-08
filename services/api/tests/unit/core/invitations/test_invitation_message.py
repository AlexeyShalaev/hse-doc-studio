"""Готовый текст приглашения: какие данные проекта в него попадают, языки, чистка значений и предел длины."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.invitations.entities import MESSAGE_MAX
from hse_doc_studio.core.invitations.message import (
    InvitationFacts,
    MessageRequest,
    ProjectPerson,
    compose_invitation_message,
)

ALEXEY = ProjectPerson(name="Шалаев Алексей Дмитриевич", email="Shalaev@edu.hse.ru", group="МСПИН261", slug="shalaev")
PETR = ProjectPerson(name="Петров Пётр", email="petr@hse.ru", group="МСПИН262", slug="petrov")
HADI = ProjectPerson(name="Хади Мухаммед")

KP_RU = InvitationFacts(
    project_name="КП Шалаев: персональный ИИ-ассистент",
    work_kind="Курсовой проект (магистратура, 1 курс)",
    documents=("Заявка на проект", "Заявление о выборе темы КП", "Отчёт о курсовом проекте", "Презентация"),
    authors=(ALEXEY, PETR),
    supervisors={"supervisor": HADI},
)
KP_EN = InvitationFacts(
    project_name="КП Шалаев: персональный ИИ-ассистент",
    work_kind="Course Project (MSc, 1st year)",
    documents=("Project proposal", "Topic application", "Course project report", "Presentation"),
    authors=(ALEXEY, PETR),
    supervisors={"supervisor": HADI},
)
SUPERVISOR = MessageRequest(
    role=Role.reviewer, persona="supervisor", inviter_name="Алексей Шалаев", inviter_email="shalaev@edu.hse.ru"
)


def test__supervisor__ru_text_uses_project_people_kind_documents_and_signature() -> None:
    text = compose_invitation_message(KP_RU, SUPERVISOR, Lang.ru)

    assert text == (
        "Здравствуйте, Хади Мухаммед!\n\n"
        "Приглашаю вас в проект «КП Шалаев: персональный ИИ-ассистент» в HSE Doc Studio в роли научного "
        "руководителя. Вид работы: курсовой проект (магистратура, 1 курс). Здесь можно смотреть документы "
        "(заявка на проект, заявление о выборе темы КП, отчёт о курсовом проекте, презентация) и оставлять "
        "замечания.\n\n"
        "С уважением,\n"
        "Алексей Шалаев, группа МСПИН261"
    )


def test__supervisor__en_text() -> None:
    text = compose_invitation_message(KP_EN, SUPERVISOR, Lang.en)

    assert text == (
        "Hello, Хади Мухаммед!\n\n"
        "I would like to invite you to the project “КП Шалаев: персональный ИИ-ассистент” in HSE Doc Studio as "
        "the supervisor. Type of work: Course Project (MSc, 1st year). Here you can view the documents "
        "(Project proposal, Topic application, Course project report, Presentation) and leave comments.\n\n"
        "Best regards,\n"
        "Алексей Шалаев, group МСПИН261"
    )


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        (
            Lang.ru,
            (
                "Здравствуйте!\n\nПриглашаю вас в проект «Диплом» в HSE Doc Studio в роли рецензента. "
                "Здесь можно смотреть документы и оставлять замечания."
            ),
        ),
        (
            Lang.en,
            (
                "Hello!\n\nI would like to invite you to the project “Диплом” in HSE Doc Studio as a reviewer. "
                "Here you can view the documents and leave comments."
            ),
        ),
    ],
)
def test__no_data__greeting_without_name_and_no_invented_phrases(lang: Lang, expected: str) -> None:
    text = compose_invitation_message(InvitationFacts(project_name="Диплом"), MessageRequest(role=Role.reviewer), lang)

    assert text == expected


def test__supervisor_persona_without_supervisor_in_project__role_kept_name_omitted() -> None:
    facts = InvitationFacts(project_name="Диплом")

    text = compose_invitation_message(facts, MessageRequest(role=Role.reader, persona="co_supervisor"), Lang.ru)

    assert text.startswith("Здравствуйте!\n\n")
    assert "в роли соруководителя." in text


def test__email_of_an_author__named_as_coauthor() -> None:
    request = MessageRequest(role=Role.editor, invitee_email=" PETR@hse.ru ")

    text = compose_invitation_message(KP_RU, request, Lang.ru)

    assert text.startswith("Здравствуйте, Петров Пётр!\n\n")
    assert "в роли соавтора." in text
    assert "Здесь можно смотреть и править документы (" in text


def test__author_slug_persona__named_as_coauthor() -> None:
    text = compose_invitation_message(KP_RU, MessageRequest(role=Role.editor, persona="petrov"), Lang.en)

    assert text.startswith("Hello, Петров Пётр!\n\n")
    assert "as a co-author." in text


def test__unknown_email_and_persona__access_role_words_without_name() -> None:
    request = MessageRequest(role=Role.reader, persona="ghost", invitee_email="nobody@hse.ru")

    text = compose_invitation_message(KP_RU, request, Lang.ru)

    assert text.startswith("Здравствуйте!\n\n")
    assert "в роли читателя." in text


@pytest.mark.parametrize(
    ("name", "email", "signature"),
    [
        ("Алексей Шалаев", "shalaev@edu.hse.ru", "Алексей Шалаев, группа МСПИН261"),
        ("Петров  пётр", "other@mail.ru", "Петров пётр, группа МСПИН262"),
        ("Анна", "anna@hse.ru", "Анна"),
    ],
)
def test__signature__group_only_for_an_author_matched_by_email_or_name(name: str, email: str, signature: str) -> None:
    request = MessageRequest(role=Role.reviewer, inviter_name=name, inviter_email=email)

    text = compose_invitation_message(KP_RU, request, Lang.ru)

    assert text.endswith(f"С уважением,\n{signature}")


def test__no_inviter_name__no_closing() -> None:
    text = compose_invitation_message(KP_RU, MessageRequest(role=Role.reviewer), Lang.ru)

    assert "С уважением" not in text


def test__topic__included_unless_it_repeats_the_project_name() -> None:
    with_topic = InvitationFacts(project_name="AI Assistant", topic="Персональный ИИ-ассистент")
    same = InvitationFacts(project_name="Диплом", topic=" диплом ")

    assert "Тема работы: «Персональный ИИ-ассистент»." in compose_invitation_message(
        with_topic, MessageRequest(role=Role.reader), Lang.ru
    )
    assert "Тема" not in compose_invitation_message(same, MessageRequest(role=Role.reader), Lang.ru)


def test__values__braces_stay_text_and_control_characters_are_removed() -> None:
    facts = InvitationFacts(project_name="{role} проект‮\x07", supervisors={"supervisor": HADI})
    request = MessageRequest(role=Role.reader, persona="supervisor", inviter_name="Анна\nПетрова")

    text = compose_invitation_message(facts, request, Lang.ru)

    assert "«{role} проект»" in text
    assert "‮" not in text
    assert "\x07" not in text
    assert text.endswith("С уважением,\nАнна Петрова")


def test__abbreviations_keep_their_case_in_ru() -> None:
    facts = InvitationFacts(project_name="Диплом", work_kind="ВКР", documents=("ТЗ", "Отчёт ВКР"))

    text = compose_invitation_message(facts, MessageRequest(role=Role.reader), Lang.ru)

    assert "Вид работы: ВКР." in text
    assert "(ТЗ, отчёт ВКР)" in text


def test__long_data__text_fits_the_limit_dropping_documents_first() -> None:
    facts = InvitationFacts(
        project_name="П" * 300,
        topic="Т" * 300,
        work_kind="Курсовой проект",
        documents=tuple(f"Документ номер {i} " + "д" * 100 for i in range(12)),
        supervisors={"supervisor": HADI},
    )

    text = compose_invitation_message(facts, SUPERVISOR, Lang.ru)

    assert len(text) <= MESSAGE_MAX
    assert "Документ номер" not in text
    assert "Вид работы: курсовой проект." in text
    assert text.endswith("С уважением,\nАлексей Шалаев")


def test__ru_and_en_templates_have_the_same_keys() -> None:
    locales = Path(__file__).parents[4] / "hse_doc_studio" / "core" / "invitations" / "locales"
    ru = json.loads((locales / "ru.json").read_text(encoding="utf-8"))
    en = json.loads((locales / "en.json").read_text(encoding="utf-8"))

    def keys(tree: dict[str, object], prefix: str = "") -> set[str]:
        out: set[str] = set()
        for key, value in tree.items():
            out |= keys(value, f"{prefix}{key}.") if isinstance(value, dict) else {f"{prefix}{key}"}
        return out

    assert keys(ru) == keys(en)
    for text in (*ru.values(), *en.values()):
        assert "—" not in str(text)
        assert "→" not in str(text)
