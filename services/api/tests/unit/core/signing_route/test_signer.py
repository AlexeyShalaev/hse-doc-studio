"""Правила действий подписанта на своей странице (docs/design/signing-route.md, разделы 4.2, 6.3, 7 и 8.1)."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signatures.plan import DocFacts, SignMethod
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    NextAction,
    ParticipantState,
    RouteConflictError,
    RouteStatus,
)
from hse_doc_studio.core.signing_route.readiness import DocChangedError
from hse_doc_studio.core.signing_route.signer import (
    APPROVE_ACTIONS,
    SIGN_ACTIONS,
    MethodNotAllowedError,
    VisibleLayerFinalError,
    acting_participant,
    available_methods,
    changed_docs,
    check_expected,
    current_method,
    doc_token,
    ensure_layer_open,
    ensure_turn,
    image_ready,
    known_plate,
    mode_for,
    own_slots,
    plates_without_signer,
    task_tokens,
    unsigned_crypto,
    with_method,
    with_signer,
)
from hse_doc_studio.core.value_objects import FrozenPdf, SignatureSlot, SignerInfo

from tests.unit.core.signing_route.world import (
    BUILD,
    DOC,
    DOC2,
    Driver,
    World,
    by_persona,
    make_route,
    participant,
    signer,
)

MARKS = "m" * 64


def _frozen(sha: str = "f" * 64, *, source: str = BUILD, marks: str = MARKS) -> FrozenPdf:
    return FrozenPdf(
        path=".hse-studio/frozen/doc.pdf",
        sha256=sha,
        source_sha256=source,
        size=1,
        frozen_at="2026-11-10T09:00:00+00:00",
        stamps_digest=marks,
    )


def _driver(modes: dict[str, SignMode], *, docs: tuple[str, ...] = (DOC,)) -> Driver:
    """Автор, научрук и академрук, каждый своим шагом, слоты на каждом из `docs`."""
    world = World(modes, docs=docs)
    route = make_route(
        [participant(step, persona, [persona], docs=docs) for step, persona in enumerate(modes, start=1)], docs=docs
    )
    return Driver(world, route)


# --- отпечатки ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "frozen", "expected"),
    [
        (NextAction.wait, None, None),
        (NextAction.done, _frozen(), None),
        (NextAction.approve, None, f"build:{BUILD}"),
        # Согласие относится к сборке, даже если документ зафиксировали до маршрута.
        (NextAction.approve, _frozen(), f"build:{BUILD}"),
        (NextAction.approve_and_sign, None, f"build:{BUILD}:{MARKS}"),
        (NextAction.approve_and_sign, _frozen(), f"pdf:{'f' * 64}"),
        (NextAction.sign, _frozen(), f"pdf:{'f' * 64}"),
        # Документ без ЭП не фиксируется: подписывающий на другом документе видел его сборку.
        (NextAction.sign, None, f"build:{BUILD}"),
        # Фиксация прежней сборки или прежнего видимого слоя это не то, что подпишет человек.
        (NextAction.approve_and_sign, _frozen(source="0" * 64), f"build:{BUILD}:{MARKS}"),
        (NextAction.approve_and_sign, _frozen(marks="1" * 64), f"build:{BUILD}:{MARKS}"),
    ],
)
def test__doc_token__by_next_action_and_freeze(
    action: NextAction, frozen: FrozenPdf | None, expected: str | None
) -> None:
    assert doc_token(action, DocFacts(BUILD, MARKS), frozen) == expected


def test__doc_token__pades_revisions_do_not_change_the_token() -> None:
    signed = replace(_frozen(), signed_path="x.signed.pdf", signed_sha256="9" * 64, signed_size=2)

    assert doc_token(NextAction.sign, DocFacts(BUILD, MARKS), signed) == f"pdf:{'f' * 64}"


def test__task_tokens__own_documents_only__approver_gets_every_route_document() -> None:
    world = World({"author": SignMode.image, "supervisor": SignMode.image}, docs=(DOC, DOC2))
    author = participant(1, "author", ["author"], docs=(DOC,))
    approver = participant(2, "academic_supervisor")
    route = make_route([author, approver], docs=(DOC, DOC2))

    mine = task_tokens(route, author, NextAction.approve, world.facts())
    everything = task_tokens(route, approver, NextAction.approve, world.facts())

    assert mine == {DOC: f"build:{BUILD}"}
    assert everything == {DOC: f"build:{BUILD}", DOC2: f"build:{BUILD}"}


def test__check_expected__mismatch_and_missing__doc_changed_with_documents() -> None:
    tokens = {DOC: "build:a", DOC2: "build:b"}

    check_expected(tokens, {DOC: "build:a", DOC2: "build:b", "other": "ignored"})
    with pytest.raises(DocChangedError) as stale:
        check_expected(tokens, {DOC: "build:a", DOC2: "build:old"})
    with pytest.raises(DocChangedError) as missing:
        check_expected(tokens, {})

    assert stale.value.doc_ids == (DOC2,)
    assert missing.value.doc_ids == (DOC, DOC2)


def test__check_expected__nothing_to_act_on__any_expected_is_stale() -> None:
    with pytest.raises(DocChangedError):
        check_expected({DOC: None}, {DOC: "build:a"})


def test__changed_docs__rebuilt_document_differs_from_the_snapshot() -> None:
    driver = _driver({"author": SignMode.image, "supervisor": SignMode.image}, docs=(DOC, DOC2))
    driver.send(by_persona(driver.route)["author"].user_id or uuid4())
    assert changed_docs(driver.route, driver.world.facts()) == ()

    driver.world.compiled[DOC2] = "c" * 64

    assert changed_docs(driver.route, driver.world.facts()) == (DOC2,)


# --- очередь --------------------------------------------------------------------------------------------------------


def test__ensure_turn__approve_only_in_own_step__sign_only_after_the_freeze() -> None:
    driver = _driver({"author": SignMode.detached_text, "supervisor": SignMode.image})
    people = by_persona(driver.route)
    driver.world.slots["author"] = replace(driver.world.slots["author"], signer=signer("author"))
    evaluation = driver.send(people["author"].user_id or uuid4())
    evaluation = driver.evaluate()
    author, supervisor = (evaluation.participant(people[p].id) for p in ("author", "supervisor"))

    ensure_turn(evaluation, supervisor, APPROVE_ACTIONS)
    with pytest.raises(RouteConflictError) as early_sign:
        ensure_turn(evaluation, author, SIGN_ACTIONS)
    with pytest.raises(RouteConflictError) as second_approval:
        ensure_turn(evaluation, author, APPROVE_ACTIONS)

    assert (early_sign.value.code, second_approval.value.code) == ("not_your_turn", "not_your_turn")


def test__ensure_turn__route_not_active__not_your_turn() -> None:
    driver = _driver({"author": SignMode.image, "supervisor": SignMode.image})
    evaluation = driver.evaluate()

    assert evaluation.status is RouteStatus.draft
    with pytest.raises(RouteConflictError) as refused:
        ensure_turn(evaluation, evaluation.participants[0], APPROVE_ACTIONS)
    assert refused.value.code == "not_your_turn"


def test__ensure_layer_open__only_while_approving_before_the_freeze() -> None:
    driver = _driver(
        {"author": SignMode.image, "supervisor": SignMode.detached_text, "academic_supervisor": SignMode.image}
    )
    people = by_persona(driver.route)
    driver.world.plates[people["supervisor"].user_id or uuid4()] = signer("supervisor")
    driver.send(people["author"].user_id or uuid4())
    evaluation = driver.evaluate()

    # Научрук согласует до фиксации: академрук ещё поставит картинку.
    ensure_layer_open(evaluation, evaluation.participant(people["supervisor"].id), people["supervisor"])
    with pytest.raises(RouteConflictError) as waiting:
        ensure_layer_open(
            evaluation, evaluation.participant(people["academic_supervisor"].id), people["academic_supervisor"]
        )
    assert waiting.value.code == "not_your_turn"


def test__ensure_layer_open__documents_frozen__visible_layer_final() -> None:
    driver = _driver({"author": SignMode.image, "supervisor": SignMode.detached_text})
    people = by_persona(driver.route)
    driver.world.plates[people["supervisor"].user_id or uuid4()] = signer("supervisor")
    driver.send(people["author"].user_id or uuid4())
    evaluation = driver.evaluate()
    view = evaluation.participant(people["supervisor"].id)

    assert view.state is ParticipantState.to_approve_sign
    with pytest.raises(VisibleLayerFinalError) as refused:
        ensure_layer_open(evaluation, view, people["supervisor"])
    assert refused.value.code == "visible_layer_final"


def test__ensure_layer_open__approver_without_slots__nothing_to_place() -> None:
    world = World({"author": SignMode.image})
    author = participant(1, "author", ["author"])
    approver = participant(2, "academic_supervisor")
    driver = Driver(world, make_route([author, approver]))
    driver.send(author.user_id or uuid4())
    evaluation = driver.evaluate()
    view = evaluation.participant(approver.id)

    assert view.state is ParticipantState.to_approve
    with pytest.raises(RouteConflictError) as refused:
        ensure_layer_open(evaluation, view, approver)
    assert refused.value.code == "not_your_turn"


def test__acting_participant__stranger__not_participant() -> None:
    driver = _driver({"author": SignMode.image})

    with pytest.raises(RouteConflictError) as refused:
        acting_participant(driver.route, driver.evaluate(), uuid4())

    assert refused.value.code == "not_participant"


def test__acting_participant__person_in_two_roles__the_one_whose_turn_it_is() -> None:
    world = World({"author": SignMode.image, "supervisor": SignMode.image})
    author = participant(1, "author", ["author"])
    same_person = replace(participant(2, "supervisor", ["supervisor"]), user_id=author.user_id)
    driver = Driver(world, make_route([author, same_person]))
    assert author.user_id is not None
    driver.send(author.user_id)

    acting = acting_participant(driver.route, driver.evaluate(), author.user_id)

    assert acting.id == same_person.id


# --- способ ---------------------------------------------------------------------------------------------------------


def test__available_methods__before_freeze_checkpoint_methods__after_it_only_the_current() -> None:
    driver = _driver({"author": SignMode.image, "supervisor": SignMode.detached_text})
    people = by_persona(driver.route)
    supervisor = people["supervisor"]
    point_methods = ("image", "detached", "pades")
    state = driver.world.state()
    driver.send(people["author"].user_id or uuid4())
    before = driver.evaluate().participant(supervisor.id)

    assert before.state is ParticipantState.to_approve
    assert available_methods(supervisor, before, state, point_methods) == (
        SignMethod.image,
        SignMethod.detached,
        SignMethod.pades,
    )
    # PAdES ставит только ключ Студии: при запрете серверных ключей его не предлагаем.
    assert available_methods(supervisor, before, state, point_methods, server_keys=False) == (
        SignMethod.image,
        SignMethod.detached,
    )

    driver.world.plates[supervisor.user_id or uuid4()] = signer("supervisor")
    driver.settle()
    after = driver.evaluate().participant(supervisor.id)

    assert after.state is ParticipantState.to_approve_sign
    assert available_methods(supervisor, after, driver.world.state(), point_methods) == (SignMethod.detached,)


def test__available_methods__approver_without_slots__nothing_to_choose() -> None:
    world = World({"author": SignMode.image})
    approver = participant(2, "academic_supervisor")
    driver = Driver(world, make_route([participant(1, "author", ["author"]), approver]))
    view = driver.evaluate().participant(approver.id)

    assert current_method(approver, world.state()) is None
    assert available_methods(approver, view, world.state(), ("image", "detached")) == ()


@pytest.mark.parametrize(
    ("method", "current", "expected"),
    [
        (SignMethod.image, SignMode.detached_text, SignMode.image),
        (SignMethod.detached, SignMode.image, SignMode.detached_text),
        (SignMethod.pades, SignMode.image, SignMode.crypto_invisible),
        # Слот уже подписывается этим способом: режим не трогаем (картинка с ЭП остаётся картинкой с ЭП).
        (SignMethod.detached, SignMode.detached, SignMode.detached),
        (SignMethod.pades, SignMode.image_crypto, SignMode.image_crypto),
        (SignMethod.image, SignMode.image, SignMode.image),
    ],
)
def test__mode_for__method_to_slot_mode(method: SignMethod, current: SignMode, expected: SignMode) -> None:
    assert mode_for(method, current) is expected


def test__with_method__image_to_plate__own_slots_change_and_leave_the_withheld_list() -> None:
    world = World({"author": SignMode.image, "supervisor": SignMode.image}, docs=(DOC, DOC2))
    supervisor = participant(2, "supervisor", ["supervisor"], docs=(DOC, DOC2))
    state = replace(world.state(), withheld={DOC: frozenset({"supervisor", "author"}), DOC2: frozenset({"supervisor"})})

    changed = with_method(state, supervisor, SignMethod.detached)

    assert changed.slots["supervisor"].sign_mode is SignMode.detached_text
    assert changed.slots["author"].sign_mode is SignMode.image
    # Плашку не придерживают: иначе расчёт её уже не открыл бы. Чужая картинка остаётся придержанной.
    assert changed.withheld == {DOC: frozenset({"author"})}
    assert changed.slots["supervisor"].png_path == state.slots["supervisor"].png_path


def test__with_method__same_method__state_unchanged() -> None:
    world = World({"supervisor": SignMode.image})
    supervisor = participant(1, "supervisor", ["supervisor"])
    state = replace(world.state(), withheld={DOC: frozenset({"supervisor"})})

    assert with_method(state, supervisor, SignMethod.image) == state


def test__with_method__back_to_image__reason_of_the_e_signature_dropped() -> None:
    world = World({"supervisor": SignMode.image_crypto})
    world.slots["supervisor"] = replace(world.slots["supervisor"], sign_reason="Согласовано")
    supervisor = participant(1, "supervisor", ["supervisor"])

    changed = with_method(world.state(), supervisor, SignMethod.image)

    assert (changed.slots["supervisor"].sign_mode, changed.slots["supervisor"].sign_reason) == (SignMode.image, "")


def test__with_signer__level_chosen_before_is_kept() -> None:
    world = World({"supervisor": SignMode.detached_text, "author": SignMode.detached_text})
    world.slots["supervisor"] = replace(world.slots["supervisor"], signer=SignerInfo("manual", "Старый", level="ukep"))
    new = SignerInfo(kind="x509", owner="Петров П. П.", cert_id="1A", signer_id="ab")

    changed = with_signer(world.state(), ["supervisor"], new)

    assert changed.slots["supervisor"].signer == replace(new, level="ukep")
    assert changed.slots["author"].signer is None


def test__with_signer__slot_without_state__created_with_the_signer() -> None:
    world = World({})

    changed = with_signer(world.state(), ["supervisor"], signer("Петров"))

    assert changed.slots["supervisor"] == SignatureSlot(None, None, None, signer=signer("Петров"))


# --- что готово у участника -----------------------------------------------------------------------------------------


def test__own_slots__unique_in_order() -> None:
    p = participant(1, "supervisor", ["supervisor"], docs=(DOC, DOC2))

    assert own_slots(p) == ("supervisor",)


def test__image_ready__every_own_slot_has_an_image_whatever_the_method() -> None:
    world = World({"supervisor": SignMode.detached_text})
    supervisor = participant(1, "supervisor", ["supervisor"])
    approver = participant(2, "academic_supervisor")

    assert image_ready(supervisor, world.facts()) is True
    world.slots["supervisor"] = replace(world.slots["supervisor"], png_path=None)
    assert image_ready(supervisor, world.facts()) is False
    assert image_ready(approver, world.facts()) is False


def test__known_plate__slot_signer_first__then_what_is_known_about_the_person() -> None:
    world = World({"supervisor": SignMode.image})
    supervisor = participant(1, "supervisor", ["supervisor"])
    assert supervisor.user_id is not None

    assert known_plate(supervisor, world.facts()) is None
    world.plates[supervisor.user_id] = signer("из профиля")
    assert known_plate(supervisor, world.facts()) == signer("из профиля")
    world.slots["supervisor"] = replace(world.slots["supervisor"], signer=signer("из слота"))
    assert known_plate(supervisor, world.facts()) == signer("из слота")


def test__plates_without_signer__only_plate_slots_lacking_the_signer() -> None:
    world = World({"supervisor": SignMode.detached_text, "author": SignMode.image})
    both = replace(
        participant(1, "supervisor", ["supervisor"]),
        assignments=(DocSlot(DOC, "supervisor"), DocSlot(DOC, "author")),
    )

    assert plates_without_signer(both, world.state()) == ("supervisor",)
    world.slots["supervisor"] = replace(world.slots["supervisor"], signer=signer("Петров"))
    assert plates_without_signer(both, world.state()) == ()


def test__unsigned_crypto__e_signature_pairs_still_waiting() -> None:
    driver = _driver({"author": SignMode.detached_text, "supervisor": SignMode.image}, docs=(DOC, DOC2))
    people = by_persona(driver.route)
    author = people["author"]
    driver.world.slots["author"] = replace(driver.world.slots["author"], signer=signer("author"))
    driver.send(author.user_id or uuid4())
    driver.act(people["supervisor"].id)

    assert unsigned_crypto(author, driver.world.facts()) == (DocSlot(DOC, "author"), DocSlot(DOC2, "author"))
    assert unsigned_crypto(people["supervisor"], driver.world.facts()) == ()

    driver.world.sign(DocSlot(DOC, "author"))

    assert unsigned_crypto(author, driver.world.facts()) == (DocSlot(DOC2, "author"),)


def test__method_not_allowed__is_a_conflict_with_its_own_code() -> None:
    error = MethodNotAllowedError()

    assert isinstance(error, RouteConflictError)
    assert error.code == "method_not_allowed"
