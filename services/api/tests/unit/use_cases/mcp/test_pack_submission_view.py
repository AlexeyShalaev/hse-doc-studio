"""Текстовый вид `pack_submission`: записанный маршрут каждой точки и «Маршрут в этой комбинации»."""

from __future__ import annotations

from hse_doc_studio.core.pack_studio.submission import (
    ExtraEntry,
    Indexed,
    ItemEntry,
    PairSource,
    ProfileRoute,
    ProfileView,
    RoutePair,
    RoutePerson,
    SkippedPair,
    SlotEntry,
    SubmissionRoutes,
    VersionSubmission,
    WhenCondition,
)
from hse_doc_studio.use_cases.mcp.tools.pack_submission_view import (
    routes_lines,
    steps_text,
    submission_lines,
    when_text,
)


def _profile(index: int, profile_id: str, **fields: object) -> ProfileView:
    base: dict[str, object] = {
        "index": index,
        "id": profile_id,
        "name": {"ru": "Итог", "en": "Final"},
        "description": {},
        "deadline_hint": None,
        "items": (),
        "extra_items": (),
        "signing_route": None,
        "signing_slots": (),
    }
    return ProfileView(**{**base, **fields})  # type: ignore[arg-type]


def _submission(*profiles: ProfileView, route: tuple[tuple[str, ...], ...] | None = None) -> VersionSubmission:
    return VersionSubmission(
        documents=("thesis", "review"),
        supported_kinds=(),
        has_nda=True,
        slots=(),
        forms=(),
        route=route,
        builtin_route=(("author",), ("supervisor", "co_supervisor"), ("academic_supervisor",)),
        profiles=profiles,
    )


def test__steps_and_when__read_as_ordered_steps_and_a_condition() -> None:
    assert steps_text((("author",), ("supervisor", "co_supervisor"))) == "1. author; 2. supervisor, co_supervisor"
    assert steps_text(()) == "-"
    assert when_text(None) == ""
    assert when_text(WhenCondition("co_supervisor")) == "если есть co_supervisor"
    assert when_text(WhenCondition("supervisor", "company")) == "если supervisor=company"


def test__submission_lines__each_point_shows_steps_signers_when_and_optional() -> None:
    final = _profile(
        0,
        "final",
        items=(
            Indexed(0, ItemEntry("thesis", ("author", "supervisor"), skip_if_nda=True, supported_kinds=("project",))),
            Indexed(1, ItemEntry("review")),
            Indexed(2, None, "items[2]: doc_id is required"),
        ),
        extra_items=(Indexed(0, ExtraEntry("forms/ai.json")),),
        signing_route=(("author",), ("co_supervisor", "supervisor")),
        signing_slots=(
            Indexed(0, SlotEntry("thesis", "co_supervisor", WhenCondition("co_supervisor"), optional=True)),
            Indexed(1, SlotEntry("review", "supervisor", WhenCondition("supervisor", "company"))),
            Indexed(2, SlotEntry("review", "author")),
            Indexed(3, None, "signing_slots[3]: unknown slot"),
        ),
    )
    draft = _profile(1, "draft", name={})

    lines = submission_lines(_submission(final, draft), "ru")

    assert lines == [
        "Порядок версии не задан, встроенный: 1. author; 2. supervisor, co_supervisor; 3. academic_supervisor",
        "  профиль 0: final «Итог»",
        "    пункт thesis: author, supervisor (не сдаётся при NDA, только project)",
        "    пункт review: без подписей",
        "    пункт [2] не читается: items[2]: doc_id is required",
        "    файлов сверх документов: 1",
        "    порядок точки (signing_route): 1. author; 2. co_supervisor, supervisor",
        "    слоты сверх точки (signing_slots):",
        "      thesis/co_supervisor (если есть co_supervisor, необязательна)",
        "      review/supervisor (если supervisor=company)",
        "      review/author",
        "      [3] не читается: signing_slots[3]: unknown slot",
        "  профиль 1: draft",
        "    порядок точки не задан: действует порядок версии",
    ]


def test__submission_lines__version_route_and_unreadable_profile() -> None:
    broken = _profile(0, None, name={}, error="profile has no id")  # type: ignore[arg-type]

    lines = submission_lines(_submission(broken, route=(("author",), ("supervisor",))), "en")

    assert lines[0] == "Порядок версии (signatures.route): 1. author; 2. supervisor"
    assert lines[1:3] == ["  профиль 0: ?", "    не читается: profile has no id"]


def test__routes_lines__steps_by_people_pairs_with_signer_source_when_and_optional() -> None:
    final = ProfileRoute(
        id="final",
        steps=(
            (RoutePerson("ivanov", "author", "Иванов Иван Иванович"),),
            (
                RoutePerson("supervisor", "supervisor", "Петров Пётр Петрович"),
                RoutePerson("co_supervisor", "co_supervisor", ""),
            ),
        ),
        pairs=(
            RoutePair("thesis", "author", "ivanov", PairSource.point, optional=False),
            RoutePair("thesis", "supervisor", "supervisor", PairSource.point, optional=True),
            RoutePair(
                "review",
                "co_supervisor",
                "co_supervisor",
                PairSource.preset,
                optional=True,
                when=WhenCondition("co_supervisor"),
            ),
        ),
        skipped=(SkippedPair("review", "supervisor", WhenCondition("supervisor", "company")),),
        may_add=(("thesis", "academic_supervisor"),),
        items_off=("nda",),
        order_source="profile",
        preset=True,
    )
    empty = ProfileRoute("draft", (), (), (), (), (), "builtin", preset=False)
    routes = SubmissionRoutes("auto:normal", {"lang": "ru", "staffing": "team2"}, (final, empty))

    assert routes_lines(routes) == [
        "Маршруты в комбинации (набор auto:normal; lang=ru, staffing=team2): профилей 2",
        "  final: порядок точки (signing_route)",
        "    шаг 1: ivanov (author) Иванов Иван Иванович",
        "    шаг 2: supervisor Петров Пётр Петрович; co_supervisor",
        "    подписи thesis: author [ivanov], supervisor (необязательна)",
        "    подписи review: co_supervisor (сверх точки, если есть co_supervisor, необязательна)",
        "    условие не пропустило: review/supervisor (если supervisor=company)",
        "    автор проекта может добавить: thesis/academic_supervisor",
        "    не сдаются в этой комбинации: nda",
        "  draft: встроенный порядок; пресета шаблона нет",
        "    подписи точке не нужны",
    ]
