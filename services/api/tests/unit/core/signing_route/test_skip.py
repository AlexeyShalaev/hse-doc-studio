"""Пропуск подписанта (docs/design/signing-route.md, раздел 13): расчёт, эффекты, переходы, перенос в раунд."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.effects import Freeze, Notify, Skip, Unskip
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    NextAction,
    ParticipantNotSkippableError,
    ParticipantState,
    RouteConflictError,
    RoutePhase,
    RouteStatus,
    SkipBlocker,
)
from hse_doc_studio.core.signing_route.transitions import send, skip
from hse_doc_studio.core.signing_route.versions import has_news
from hse_doc_studio.core.value_objects import FrozenPdf

from tests.unit.core.signing_route.world import (
    DOC,
    DOC2,
    T0,
    Driver,
    World,
    by_persona,
    make_route,
    participant,
    signer,
)

_EP = SignMode.detached_text
_PERSONAS = ("author", "supervisor", "academic_supervisor")


def _route(modes: dict[str, SignMode], *, optional: tuple[str, ...] = ("academic_supervisor",)) -> Driver:
    """Автор, научрук, академрук по шагам; необязательны слоты `optional` на DOC."""
    world = World(modes=modes)
    if modes["author"] is _EP:  # плашка отправителя готова к отправке (`sender_not_ready` иначе)
        world.slots["author"] = replace(world.slots["author"], signer=signer("author"))
    world.optional[DOC] = set(optional)
    people = [participant(step, persona, [persona]) for step, persona in enumerate(_PERSONAS, start=1)]
    return Driver(world, make_route(people))


def _sent(driver: Driver) -> Driver:
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    driver.send(by=author.user_id)
    return driver


def _approve_plates(driver: Driver) -> None:
    """Отправитель с плашкой согласовал при отправке (ключ у него задан); шаг 2: научрук."""
    driver.act(by_persona(driver.route)["supervisor"].id)


def _approve_to_academic(driver: Driver) -> None:
    """Автор отправил, научрук согласовал: очередь академрука (шаг 3 из 3)."""
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)


# --- возможность пропуска -------------------------------------------------------------------------------------------


def test__skip_option__academic_in_turn_with_optional_slot__is_available() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    _approve_to_academic(driver)
    academic = by_persona(driver.route)["academic_supervisor"]

    option = driver.evaluate().participant(academic.id).skip

    assert option.available
    assert option.pairs == (DocSlot(DOC, "academic_supervisor"),)
    assert option.keeps_marks == ()
    assert option.refreezes == ()


def test__skip_option__required_slot__blocks_and_names_the_slot() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image), optional=()))
    _approve_to_academic(driver)
    academic = by_persona(driver.route)["academic_supervisor"]

    option = driver.evaluate().participant(academic.id).skip

    assert not option.available
    assert option.blocker is SkipBlocker.required_slots
    assert option.required == (DocSlot(DOC, "academic_supervisor"),)


def test__skip_option__not_his_turn__blocks() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    academic = by_persona(driver.route)["academic_supervisor"]

    option = driver.evaluate().participant(academic.id).skip

    assert option.blocker is SkipBlocker.not_turn


def test__skip_option__approver_without_slots__is_not_skippable() -> None:
    world = World(modes={"author": SignMode.image})
    people = [participant(1, "author", ["author"]), participant(2, "supervisor")]
    driver = _sent(Driver(world, make_route(people)))
    approver = by_persona(driver.route)["supervisor"]

    option = driver.evaluate().participant(approver.id).skip

    assert option.blocker is SkipBlocker.no_slots


def test__skip_option__finished_participant__is_done() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    author = by_persona(driver.route)["author"]

    assert driver.evaluate().participant(author.id).skip.blocker is SkipBlocker.done


def test__skip_option__invited_on_current_step__is_available_but_not_on_a_later_one() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    people = by_persona(driver.route)
    driver.route = driver.route.with_participant(replace(people["supervisor"], approval=None))
    _approve_to_academic_invited(driver)
    academic = by_persona(driver.route)["academic_supervisor"]

    option = driver.evaluate().participant(academic.id).skip

    assert driver.evaluate().participant(academic.id).state is ParticipantState.invited
    assert option.available


def _approve_to_academic_invited(driver: Driver) -> None:
    """Научрук согласовал, академрук не принял приглашение (user_id пуст)."""
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)
    driver.route = driver.route.with_participant(replace(people["academic_supervisor"], user_id=None))


def test__skip_option__invited_on_a_later_step__is_not_his_turn() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    academic = by_persona(driver.route)["academic_supervisor"]
    driver.route = driver.route.with_participant(replace(academic, user_id=None))

    assert driver.evaluate().participant(academic.id).skip.blocker is SkipBlocker.not_turn


# --- переход и расчёт: пропуск последнего шага -----------------------------------------------------------------------


def test__skip__last_step_images__route_completes_and_record_is_written() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    _approve_to_academic(driver)
    academic = by_persona(driver.route)["academic_supervisor"]

    evaluation = driver.skip(academic.id)

    assert driver.route.status is RouteStatus.completed
    assert evaluation.participant(academic.id).state is ParticipantState.skipped
    assert evaluation.participant(academic.id).next_action is NextAction.done
    record = driver.world.skipped[DOC]["academic_supervisor"]
    assert (record.route_id, record.round, record.keep_mark) == (str(driver.route.id), 1, False)
    assert any(isinstance(e, Notify) and e.notice.value == "signing_completed" for e in driver.world.notices)


def test__skip__image_withheld__stays_withheld_and_digest_is_unchanged() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    _approve_to_academic(driver)
    academic = by_persona(driver.route)["academic_supervisor"]
    before = driver.world.marks(DOC)

    driver.skip(academic.id)

    assert "academic_supervisor" in driver.world.withheld[DOC]
    assert driver.world.marks(DOC) == before
    assert not driver.world.image_visible(DocSlot(DOC, "academic_supervisor"))


def test__skip__only_the_participants_in_turn_and_active_route() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    academic = by_persona(driver.route)["academic_supervisor"]

    with pytest.raises(ParticipantNotSkippableError) as raised:
        skip(driver.route, driver.world.facts(), academic.id, by=uuid4(), at=T0)
    assert raised.value.code == "participant_not_skippable"
    assert raised.value.reason is SkipBlocker.not_turn

    paused = replace(driver.route, status=RouteStatus.paused)
    with pytest.raises(RouteConflictError) as invalid:
        skip(paused, driver.world.facts(), academic.id, by=uuid4(), at=T0)
    assert invalid.value.code == "invalid_transition"


def test__skip__required_slots__raises_with_the_slots() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image), optional=()))
    _approve_to_academic(driver)
    academic = by_persona(driver.route)["academic_supervisor"]

    with pytest.raises(ParticipantNotSkippableError) as raised:
        driver.skip(academic.id)

    assert raised.value.reason is SkipBlocker.required_slots
    assert raised.value.slots == (DocSlot(DOC, "academic_supervisor"),)


def test__skip__is_idempotent_after_effects() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    _approve_to_academic(driver)
    driver.skip(by_persona(driver.route)["academic_supervisor"].id)

    assert evaluate(driver.route, driver.world.facts()).effects == ()


def test__skip__record_lost_in_files__comes_back_with_the_next_evaluation() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    _approve_to_academic(driver)
    driver.skip(by_persona(driver.route)["academic_supervisor"].id)
    driver.world.skipped.clear()  # git затёр запись

    effects = driver.evaluate().effects

    assert Skip(DOC, "academic_supervisor", False) in effects


# --- метки и фиксация (таблица 13.5) ---------------------------------------------------------------------------------


def test__skip__plate_before_freeze__freezes_without_the_mark_in_the_same_evaluation() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, _EP)))
    _approve_plates(driver)
    academic = by_persona(driver.route)["academic_supervisor"]
    assert driver.evaluate().phase is RoutePhase.approval

    evaluation = driver.skip(academic.id)

    assert evaluation.phase is RoutePhase.signing
    assert DOC in driver.world.frozen
    assert "plate:academic_supervisor" not in driver.world.frozen[DOC].stamps_digest
    assert driver.world.frozen[DOC].stamps_digest == driver.world.marks(DOC)
    assert driver.world.resets == 0
    assert driver.route.status is RouteStatus.active  # ждём ЭП автора и научрука


def test__skip__then_the_rest_sign__route_completes() -> None:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, _EP)))
    _approve_plates(driver)
    driver.skip(by_persona(driver.route)["academic_supervisor"].id)

    driver.run()

    assert driver.route.status is RouteStatus.completed
    assert driver.world.resets == 0
    assert set(driver.world.detached[DOC]) == {"author", "supervisor"}


def _approved_unsigned_academic(*, sign_author: bool) -> Driver:
    """Все согласовали, B зафиксирован с плашкой академрука; академрук не подписал (to_sign)."""
    driver = _sent(_route(dict.fromkeys(_PERSONAS, _EP)))
    _approve_plates(driver)
    people = by_persona(driver.route)
    driver._approve(people["academic_supervisor"].id, combined=False)  # noqa: SLF001
    assert driver.evaluate().participant(people["academic_supervisor"].id).state is ParticipantState.to_sign
    if sign_author:
        driver.world.sign(DocSlot(DOC, "author"))
        driver.settle()
    return driver


def test__skip__mark_in_frozen_pdf_with_signatures__keeps_the_mark_and_the_signatures() -> None:
    driver = _approved_unsigned_academic(sign_author=True)
    academic = by_persona(driver.route)["academic_supervisor"]
    frozen_before = driver.world.frozen[DOC]

    option = driver.evaluate().participant(academic.id).skip
    evaluation = driver.skip(academic.id)

    assert option.keeps_marks == (DOC,)
    assert option.refreezes == ()
    assert driver.world.skipped[DOC]["academic_supervisor"].keep_mark
    assert driver.route.participant(academic.id).skipped is not None
    assert driver.route.participant(academic.id).skipped.kept_marks == (DOC,)  # type: ignore[union-attr]
    assert driver.world.frozen[DOC] == frozen_before
    assert driver.world.resets == 0
    assert DocSlot(DOC, "author") in {DocSlot(DOC, s) for s in driver.world.detached[DOC]}
    assert not any(isinstance(e, Freeze) for e in evaluation.effects)


def test__skip__mark_in_frozen_pdf_without_signatures__refreezes_without_the_mark() -> None:
    driver = _approved_unsigned_academic(sign_author=False)
    academic = by_persona(driver.route)["academic_supervisor"]
    frozen_before = driver.world.frozen[DOC]

    option = driver.evaluate().participant(academic.id).skip
    evaluation = driver.skip(academic.id)

    assert option.keeps_marks == ()
    assert option.refreezes == (DOC,)
    assert Skip(DOC, "academic_supervisor", False) in evaluation.effects
    assert Freeze(DOC) in evaluation.effects
    assert driver.world.frozen[DOC].sha256 != frozen_before.sha256
    assert driver.world.frozen[DOC].stamps_digest == driver.world.marks(DOC)
    assert driver.route.participant(academic.id).skipped.refrozen == (DOC,)  # type: ignore[union-attr]
    assert driver.route.status is RouteStatus.active


def test__skip__refreeze_makes_a_waiting_signer_see_another_pdf() -> None:
    driver = _approved_unsigned_academic(sign_author=False)
    author_sha = driver.world.frozen[DOC].sha256

    driver.skip(by_persona(driver.route)["academic_supervisor"].id)

    # Подписант, открывший страницу с прежним отпечатком, получит `doc_changed`: B другой.
    assert driver.world.frozen[DOC].sha256 != author_sha


def test__skip__pades_slot_without_mark__does_not_touch_the_frozen_pdf() -> None:
    modes = {"author": _EP, "supervisor": _EP, "academic_supervisor": SignMode.crypto_invisible}
    driver = _sent(_route(modes))
    _approve_plates(driver)
    people = by_persona(driver.route)
    driver.act(people["academic_supervisor"].id)  # согласовал и подписал: фиксация без метки академрука
    frozen_before = driver.world.frozen.get(DOC)

    option = driver.evaluate().participant(people["academic_supervisor"].id).skip

    assert frozen_before is not None
    assert option.blocker is SkipBlocker.done  # подписал: пропускать нечего


def test__skip__invisible_pades_not_yet_signed__skips_without_touching_the_frozen_pdf() -> None:
    modes = {"author": _EP, "supervisor": _EP, "academic_supervisor": SignMode.crypto_invisible}
    driver = _sent(_route(modes))
    _approve_plates(driver)
    people = by_persona(driver.route)
    driver._approve(people["academic_supervisor"].id, combined=False)  # noqa: SLF001
    frozen_before = driver.world.frozen[DOC]

    option = driver.evaluate().participant(people["academic_supervisor"].id).skip
    driver.skip(people["academic_supervisor"].id)

    assert option.available
    assert option.keeps_marks == ()
    assert option.refreezes == ()
    assert driver.world.frozen[DOC] == frozen_before
    assert driver.world.resets == 0


# --- сценарий владельца: шаг 3 из 3, академрук не принял приглашение -------------------------------------------------


def _owner_world(*, stale_manual_freeze: bool, other_signers_on_topic: bool) -> Driver:
    """Заявка на тему (DOC): автор и академрук (его слот сверх точки, необязателен); у научрука на предложении (DOC2)
    картинка. Ручная фиксация заявки от 09.11 устарела: видимый слой после неё изменился."""
    modes = {"author": _EP if other_signers_on_topic else SignMode.image, "supervisor": SignMode.image}
    modes["academic_supervisor"] = _EP
    world = World(modes=modes, docs=(DOC, DOC2))
    if modes["author"] is _EP:
        world.slots["author"] = replace(world.slots["author"], signer=signer("author"))
    world.optional[DOC] = {"academic_supervisor"}
    if stale_manual_freeze:
        world.frozen[DOC] = FrozenPdf(
            path=".hse-studio/frozen/manual.pdf",
            sha256="c" * 64,
            source_sha256="b" * 64,
            size=1,
            frozen_at="2026-11-09T10:00:00+00:00",
            stamps_digest="stale",
        )
    people = [
        participant(1, "author", ["author"], docs=(DOC,)),
        participant(2, "supervisor", ["supervisor"], docs=(DOC2,)),
        replace(participant(3, "academic_supervisor", ["academic_supervisor"], docs=(DOC,)), user_id=None),
    ]
    return Driver(world, make_route(people, docs=(DOC, DOC2)))


def test__owner_scenario__invited_academic_skipped__completes_and_does_not_refreeze_a_document_without_signers() -> (
    None
):
    driver = _owner_world(stale_manual_freeze=True, other_signers_on_topic=False)
    driver.world.pin((DOC, DOC2))
    _sent(driver)
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)
    academic = by_persona(driver.route)["academic_supervisor"]
    assert driver.evaluate().participant(academic.id).state is ParticipantState.invited
    assert driver.evaluate().participant(academic.id).skip.available

    evaluation = driver.skip(academic.id)

    # На заявке не осталось непропущенных слотов ЭП: маршрут её не фиксирует (инвариант 6), ручная фиксация цела.
    assert evaluation.status is RouteStatus.completed
    assert not any(isinstance(e, Freeze) for e in evaluation.effects)
    assert driver.world.frozen[DOC].path == ".hse-studio/frozen/manual.pdf"
    assert driver.world.skipped[DOC]["academic_supervisor"].keep_mark is False


@pytest.mark.parametrize("signed_over_manual", [False, True])
def test__owner_scenario__other_signers_on_the_document__stale_manual_freeze_is_refrozen_by_the_route(
    signed_over_manual: bool,
) -> None:
    driver = _owner_world(stale_manual_freeze=True, other_signers_on_topic=True)
    if signed_over_manual:
        driver.world.sign(DocSlot(DOC, "author"))  # ЭП автора над ручной фиксацией
    _sent(driver)
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)
    academic = by_persona(driver.route)["academic_supervisor"]

    evaluation = driver.skip(academic.id)

    assert driver.route.status is RouteStatus.active  # ждём ЭП автора
    assert Freeze(DOC) in evaluation.effects
    assert driver.world.frozen[DOC].path != ".hse-studio/frozen/manual.pdf"
    assert driver.world.frozen[DOC].stamps_digest == driver.world.marks(DOC)
    # Подписи над прежним B сбрасывает перефиксация по прежним правилам 6.2, пропуск тут ни при чём.
    assert driver.world.resets == int(signed_over_manual)
    assert not driver.world.detached.get(DOC)


# --- частичная подпись ---------------------------------------------------------------------------------------------


def test__skip__partly_signed_participant__only_the_remaining_pairs_are_skipped() -> None:
    world = World(modes={"academic_supervisor": _EP, "author": _EP}, docs=(DOC, DOC2))
    world.slots["author"] = replace(world.slots["author"], signer=signer("author"))
    world.optional[DOC2] = {"academic_supervisor"}
    people = [
        participant(1, "author", ["author"], docs=(DOC, DOC2)),
        participant(2, "academic_supervisor", ["academic_supervisor"], docs=(DOC, DOC2)),
    ]
    driver = _sent(Driver(world, make_route(people, docs=(DOC, DOC2))))
    academic = by_persona(driver.route)["academic_supervisor"]
    driver.act(academic.id)  # согласовал (и подписал)
    # DOC уже подписан академруком, а на DOC2 подпись пропала (например, зафиксировали заново).
    world.unsign(DocSlot(DOC2, "academic_supervisor"))
    driver.settle()
    academic = by_persona(driver.route)["academic_supervisor"]

    option = driver.evaluate().participant(academic.id).skip

    assert option.available
    assert option.pairs == (DocSlot(DOC2, "academic_supervisor"),)
    driver.skip(academic.id)
    assert world.is_signed(DocSlot(DOC, "academic_supervisor"))
    assert DOC not in world.skipped or "academic_supervisor" not in world.skipped[DOC]


# --- новый раунд ---------------------------------------------------------------------------------------------------


def _skipped_route() -> Driver:
    driver = _sent(_route(dict.fromkeys(_PERSONAS, SignMode.image)))
    _approve_to_academic(driver)
    driver.skip(by_persona(driver.route)["academic_supervisor"].id)
    return driver


def test__send__skip_is_carried_into_the_new_round_while_the_slot_stays_optional() -> None:
    driver = _skipped_route()
    driver.world.compiled[DOC] = "d" * 64  # документ изменился
    candidate = driver.world.facts().candidate()
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None

    sent = send(driver.route, candidate, by=author.user_id, at=T0)

    academic = sent.participant(by_persona(driver.route)["academic_supervisor"].id)
    assert academic.skipped is not None
    assert academic.skipped.round == sent.round == 2
    driver.route = sent
    driver.world.pin((DOC,))
    driver.settle()
    assert driver.evaluate().participant(academic.id).state is ParticipantState.skipped
    assert DOC in driver.world.skipped  # запись осталась


def test__send__slot_no_longer_optional__skip_is_dropped_and_the_record_removed() -> None:
    driver = _skipped_route()
    driver.world.optional[DOC].discard("academic_supervisor")
    driver.world.compiled[DOC] = "d" * 64
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    candidate = driver.world.facts().candidate()
    driver.route = send(driver.route, candidate, by=author.user_id, at=T0)
    driver.world.pin((DOC,))

    evaluation = driver.settle()

    academic = by_persona(driver.route)["academic_supervisor"]
    assert academic.skipped is None
    assert Unskip(DOC, "academic_supervisor") in evaluation.effects
    assert driver.world.skipped.get(DOC, {}) == {}
    assert "academic_supervisor" in driver.world.withheld[DOC]
    assert driver.evaluate().participant(academic.id).state is not ParticipantState.skipped


def test__send__without_changes__is_nothing_changed_unless_somebody_returns() -> None:
    driver = _skipped_route()
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    candidate = driver.world.facts().candidate()

    assert not has_news(driver.route, candidate)
    with pytest.raises(RouteConflictError) as raised:
        send(driver.route, candidate, by=author.user_id, at=T0)
    assert raised.value.code == "nothing_changed"

    driver.world.optional[DOC].discard("academic_supervisor")  # отметку сняли, маршрут держит документ
    candidate = driver.world.facts().candidate()
    assert has_news(driver.route, candidate)
    sent = send(driver.route, candidate, by=author.user_id, at=T0)
    assert sent.participant(by_persona(driver.route)["academic_supervisor"].id).skipped is None


def test__skip__removing_the_flag_keeps_the_skip_until_the_next_round() -> None:
    driver = _skipped_route()
    driver.world.optional[DOC].discard("academic_supervisor")

    evaluation = driver.evaluate()

    academic = by_persona(driver.route)["academic_supervisor"]
    assert evaluation.participant(academic.id).state is ParticipantState.skipped
    assert evaluation.effects == ()
    assert driver.route.status is RouteStatus.completed
