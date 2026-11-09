"""Порядок маршрута подписания по умолчанию (docs/design/signing-route.md, раздел 5.2).

Пак задаёт порядок шагами из id слотов каталога: `signatures.route` версии и `signing_route` профиля сдачи,
который переопределяет версию для своей точки. Внутри шага подписывают параллельно. Без ключей действует
встроенный порядок: авторы, затем научный руководитель и соруководитель (консультант) одним шагом, затем
академический руководитель. Ему следуют выпущенные версии hse-cs-sse и hse-cs-se: их каталоги неизменны и новых
ключей не получат.

Порядок служит заготовкой черновика маршрута, автор меняет его до отправки. Результат нейтральный, без
сущностей маршрута: шаги из персон подписантов (`slot_persona`), внутри шага параллельно.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from hse_doc_studio.core.catalog import PackSubmissionConfig, SubmissionProfile, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.signatures.plan import slot_persona
from hse_doc_studio.core.team import split_instance_id

# Шаги маршрута: id слотов каталога (`route_order`) или персоны подписантов (`default_route`).
type RouteSteps = tuple[tuple[str, ...], ...]

BUILTIN_ROUTE: RouteSteps = (("author",), ("supervisor", "co_supervisor"), ("academic_supervisor",))


def route_order(version: TemplateVersion, profile: SubmissionProfile | None = None) -> RouteSteps:
    """Шаги из id слотов каталога: порядок точки, иначе порядок версии, иначе встроенный.

    Неизвестные id и повторы пропускаются (действует первое упоминание), пустые шаги отбрасываются. Слот
    каталога, которого нет в порядке, идёт отдельным шагом в конце, в порядке объявления слотов. Так в
    результате каждый слот каталога стоит ровно на одном шаге.
    """
    declared = (profile.signing_route if profile is not None else ()) or version.signatures_config.route
    catalog = [slot.id for slot in version.signatures_config.slots]
    known = set(catalog)
    placed: set[str] = set()
    steps: list[tuple[str, ...]] = []
    for step in declared or BUILTIN_ROUTE:
        kept = tuple(dict.fromkeys(slot_id for slot_id in step if slot_id in known and slot_id not in placed))
        placed.update(kept)
        if kept:
            steps.append(kept)
    steps.extend((slot_id,) for slot_id in catalog if slot_id not in placed)
    return tuple(steps)


def default_route(
    version: TemplateVersion,
    profile: SubmissionProfile,
    project: Project,
    *,
    slot_ids: Iterable[str] | None = None,
) -> RouteSteps:
    """Заготовка маршрута точки для проекта: шаги из персон подписантов, внутри шага параллельно.

    `slot_ids` рантайм-слоты маршрута (`author--<слаг>` в команде). По умолчанию это слоты, которые точка требует
    в этом проекте: те же пары «документ, слот», что у плана подписей точки. Необязательный слот, добавленный
    автором, передаётся здесь же и встаёт на шаг своего слота каталога.

    Слот `per_author` в команде раскрывается в персоны всех его авторов на одном шаге, в порядке авторов проекта.
    Персона стоит на первом шаге, где у неё есть слот: участник маршрута один на персону. Шаги без слотов
    отбрасываются; пустой результат значит, что точке подписи не нужны.
    """
    wanted = list(dict.fromkeys(slot_ids if slot_ids is not None else _required_slot_ids(version, profile, project)))
    runtime_index = {slot.id: i for i, slot in enumerate(SignatureSlotService().runtime_slots(project, version))}
    wanted.sort(key=lambda slot_id: runtime_index.get(slot_id, len(runtime_index)))
    by_base: dict[str, list[str]] = {}
    for slot_id in wanted:
        by_base.setdefault(split_instance_id(slot_id)[0], []).append(slot_id)

    order = route_order(version, profile)
    in_order = {base for step in order for base in step}
    # Слот не из каталога (каталог версии сменился) не теряется: отдельный шаг в конце, как в `route_order`.
    steps = [*order, *((base,) for base in by_base if base not in in_order)]
    seen: set[str] = set()
    result: list[tuple[str, ...]] = []
    for step in steps:
        personas = tuple(
            dict.fromkeys(
                persona
                for base in step
                for slot_id in by_base.get(base, ())
                if (persona := slot_persona(slot_id)) not in seen
            )
        )
        seen.update(personas)
        if personas:
            result.append(personas)
    return tuple(result)


def _required_slot_ids(version: TemplateVersion, profile: SubmissionProfile, project: Project) -> list[str]:
    """Рантайм-слоты, подпись которых точка требует в этом проекте (гейты пунктов как у сборки пакета)."""
    only_profile = replace(version, pack_submission=PackSubmissionConfig(profiles=(profile,)))
    return list(SignatureSlotService().required_by_profiles(project, only_profile))
