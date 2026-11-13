"""Дата подписания в расчёте маршрута (docs/design/signing-route.md, 14.4 и 14.5).

Метки даты делают участника меняющим видимый слой, пока он не согласовал; при согласии маршрут пишет момент
согласия (`RecordSignedAt`), у уже согласовавшего дозаполняет его из `Approval.at`; новая версия с тем же
отпечатком дату не меняет, с другим меняет после нового согласия.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from hse_doc_studio.core.enums import SignedAtSource, SignMode
from hse_doc_studio.core.signing_route.effects import Freeze, RecordSignedAt
from hse_doc_studio.core.signing_route.engine import approval_token
from hse_doc_studio.core.signing_route.entities import DocSlot, NextAction, ParticipantState, RoutePhase, RouteStatus
from hse_doc_studio.core.signing_route.transitions import approve, refresh_snapshot, send
from hse_doc_studio.core.value_objects import SignedAt

from tests.unit.core.signing_route.world import (
    DOC,
    DOC2,
    Driver,
    World,
    by_persona,
    make_route,
    participant,
    sha,
    signer,
)

_IMG = SignMode.image
_EP = SignMode.detached_text
_PERSONAS = ("author", "supervisor", "academic_supervisor")


def _trio(modes: dict[str, SignMode], *, docs: tuple[str, ...] = (DOC,)) -> Driver:
    """Автор, научрук, академрук по шагам; у плашек ключ известен (данные подписанта в слоте)."""
    world = World(modes=modes, docs=docs)
    for slot_id, mode in modes.items():
        if mode is _EP:
            world.slots[slot_id] = replace(world.slots[slot_id], signer=signer(slot_id))
    people = [participant(step, persona, [persona], docs=docs) for step, persona in enumerate(_PERSONAS, start=1)]
    return Driver(world, make_route(people, docs=docs))


def _send(driver: Driver) -> None:
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    driver.send(by=author.user_id)


def _approval_at(driver: Driver, persona: str) -> datetime:
    approval = by_persona(driver.route)[persona].approval
    assert approval is not None
    return approval.at


def test__date_marks__make_an_unapproved_signer_a_changer__esign_after_freeze_takes_two_actions() -> None:
    """Подписанты ЭП с известными ключами без меток согласуют и подписывают одним действием после фиксации при
    отправке (L = 0). С метками даты они меняют видимый слой до согласия (14.4): фиксация ждёт последнего из них,
    а научрук, который не последний, делает два действия; редактор маршрута видит это числом действий (4.4)."""
    modes = {"author": _IMG, "supervisor": _EP, "academic_supervisor": _EP}
    plain, dated = _trio(modes), _trio(modes)
    dated.world.add_dates(DocSlot(DOC, "supervisor"))
    dated.world.add_dates(DocSlot(DOC, "academic_supervisor"))
    _send(plain)
    _send(dated)

    def views(driver: Driver) -> dict[str, tuple[bool, NextAction, int]]:
        evaluation = driver.evaluate()
        return {
            p.persona: (v.changes_visible, v.next_action, v.remaining_actions)
            for p in driver.route.participants
            if (v := evaluation.participant(p.id)) is not None
        }

    assert plain.evaluate().last_visible_step == 0
    assert views(plain)["supervisor"] == (False, NextAction.approve_and_sign, 1)
    assert dated.evaluate().last_visible_step == 3
    assert dated.evaluate().phase is RoutePhase.approval
    assert views(dated)["supervisor"] == (True, NextAction.approve, 2)
    assert views(dated)["academic_supervisor"] == (True, NextAction.wait, 1)
    assert DOC not in dated.world.frozen


def test__date_marks__last_changer_esign__combines_approval_and_signature() -> None:
    """Научрук ЭП с меткой даты последний, кто меняет видимый слой: согласует и подписывает одним действием, его дата
    уже в B (фиксация после записи даты)."""
    driver = _trio({"author": _IMG, "supervisor": _EP, "academic_supervisor": _IMG})
    driver.world.add_dates(DocSlot(DOC, "supervisor"), 3)
    driver.route = replace(driver.route, participants=driver.route.participants[:2])
    _send(driver)
    supervisor = by_persona(driver.route)["supervisor"]

    view = driver.evaluate().participant(supervisor.id)
    assert (view.changes_visible, view.next_action, view.remaining_actions) == (True, NextAction.approve_and_sign, 1)
    driver.act(supervisor.id)

    pair = DocSlot(DOC, "supervisor")
    recorded = driver.world.signed_at[pair]
    assert recorded.source is SignedAtSource.approval
    assert recorded.token == approval_token(driver.world.doc_facts(DOC))
    assert datetime.fromisoformat(recorded.at) == _approval_at(driver, "supervisor")
    assert driver.world.frozen[DOC].stamps_digest == driver.world.marks(DOC)
    assert driver.world.is_signed(pair)
    assert driver.route.status is RouteStatus.completed


def test__record_signed_at__at_approval__moment_and_token_of_the_document() -> None:
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _IMG})
    pair = DocSlot(DOC, "supervisor")
    driver.world.add_dates(pair, 3)
    _send(driver)
    supervisor = by_persona(driver.route)["supervisor"]

    driver.act(supervisor.id)

    assert driver.world.signed_at[pair] == SignedAt(
        at=_approval_at(driver, "supervisor").astimezone(UTC).isoformat(timespec="seconds"),
        source=SignedAtSource.approval,
        token=approval_token(driver.world.doc_facts(DOC)),
    )
    # Дата академрука ещё не известна: его согласия нет.
    assert DocSlot(DOC, "academic_supervisor") not in driver.world.signed_at


def test__record_signed_at__marks_added_after_approval__backfilled_from_approval_at() -> None:
    """Живой случай (14.5): научрук согласовал картинкой до появления меток; метки добавлены на идущем маршруте,
    следующий расчёт дозаполняет дату из `Approval.at`, ничего не останавливая и не фиксируя."""
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _IMG})
    _send(driver)
    supervisor = by_persona(driver.route)["supervisor"]
    driver.act(supervisor.id)
    pair = DocSlot(DOC, "supervisor")
    assert pair not in driver.world.signed_at

    driver.world.add_dates(pair, 3)
    driver.route = refresh_snapshot(driver.route, driver.world.facts())  # правку меток принял сценарий маршрута
    evaluation = driver.evaluate()

    records = [e for e in evaluation.effects if isinstance(e, RecordSignedAt)]
    token = approval_token(driver.world.doc_facts(DOC))
    assert records == [RecordSignedAt(DOC, "supervisor", _approval_at(driver, "supervisor"), token)]
    assert not any(isinstance(e, Freeze) for e in evaluation.effects)
    assert (evaluation.status, evaluation.stop) == (RouteStatus.active, None)
    driver.settle()
    assert datetime.fromisoformat(driver.world.signed_at[pair].at) == _approval_at(driver, "supervisor")
    view = driver.evaluate().participant(by_persona(driver.route)["academic_supervisor"].id)
    assert view.state is ParticipantState.to_approve


def test__record_signed_at__skipped_or_unapproved_pair__nothing_recorded() -> None:
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _IMG})
    driver.world.add_dates(DocSlot(DOC, "academic_supervisor"))
    _send(driver)

    assert not [e for e in driver.evaluate().effects if isinstance(e, RecordSignedAt)]


def test__record_signed_at__new_version__same_document_keeps_the_date__changed_one_gets_the_new_approval() -> None:
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _IMG}, docs=(DOC, DOC2))
    kept, changed = DocSlot(DOC, "supervisor"), DocSlot(DOC2, "supervisor")
    driver.world.add_dates(kept)
    driver.world.add_dates(changed)
    _send(driver)
    supervisor = by_persona(driver.route)["supervisor"]
    driver.act(supervisor.id)
    first = dict(driver.world.signed_at)

    # Новая версия: DOC2 пересобран, DOC тот же. Согласие перенесено с прежними отпечатками.
    driver.world.compiled[DOC2] = sha("v2")
    _send(driver)
    assert driver.world.signed_at == first
    driver.act(supervisor.id)

    assert driver.world.signed_at[kept] == first[kept]
    assert driver.world.signed_at[changed] != first[changed]
    assert driver.world.signed_at[changed].token == approval_token(driver.world.doc_facts(DOC2))
    assert datetime.fromisoformat(driver.world.signed_at[changed].at) == _approval_at(driver, "supervisor")


def test__record_signed_at__sender_resends_without_changes__date_stays() -> None:
    """Отправитель: его согласие это отправка; повторная отправка с тем же документом дату не меняет (14.5)."""
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _IMG})
    pair = DocSlot(DOC, "author")
    driver.world.add_dates(pair)
    _send(driver)
    first = driver.world.signed_at[pair]
    driver.route = replace(driver.route, status=RouteStatus.paused, phase=None)

    _send(driver)

    assert driver.world.signed_at[pair] == first
    assert _approval_at(driver, "author") > datetime.fromisoformat(first.at)


def test__record_signed_at__day_changes_on_a_frozen_document__refrozen_in_the_same_pass() -> None:
    """Дата согласия на документе, уже зафиксированном в фазе `signing`: документ тронут, его фиксируют заново
    после записи даты (14.6, шаг 3)."""
    driver = _trio({"author": _EP, "supervisor": _EP, "academic_supervisor": _EP})
    driver.route = replace(driver.route, participants=driver.route.participants[:2])
    _send(driver)
    supervisor = by_persona(driver.route)["supervisor"]
    driver.act(supervisor.id)  # согласовать и подписать: L = 0, документ зафиксирован при отправке
    assert driver.route.status is RouteStatus.active  # автор ещё не подписал свою ЭП
    pair = DocSlot(DOC, "supervisor")
    driver.world.add_dates(pair)
    driver.route = refresh_snapshot(driver.route, driver.world.facts())

    evaluation = driver.evaluate()
    files = [e for e in evaluation.effects if isinstance(e, RecordSignedAt | Freeze)]

    assert [type(e) for e in files] == [RecordSignedAt, Freeze]
    assert evaluation.phase is RoutePhase.signing


def test__approve__dated_signer__records_before_freeze_and_marks_digest_matches() -> None:
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _EP})
    driver.world.add_dates(DocSlot(DOC, "academic_supervisor"), 3)
    _send(driver)
    driver.run()

    assert driver.route.status is RouteStatus.completed
    assert DocSlot(DOC, "academic_supervisor") in driver.world.signed_at
    assert driver.world.frozen[DOC].stamps_digest == driver.world.marks(DOC)
    assert driver.world.resets == 0


def test__approve_transition__unchanged_by_dates() -> None:
    """`approve` пишет согласие как раньше; дату пишет расчёт, а не переход."""
    driver = _trio({"author": _IMG, "supervisor": _IMG, "academic_supervisor": _IMG})
    driver.world.add_dates(DocSlot(DOC, "supervisor"))
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    driver.route = send(driver.route, driver.world.facts().candidate(), by=author.user_id, at=driver.tick())
    supervisor = by_persona(driver.route)["supervisor"]

    approved = approve(driver.route, driver.world.facts(), supervisor.id, at=driver.tick())

    assert approved.participant(supervisor.id).approval is not None
    assert DocSlot(DOC, "supervisor") not in driver.world.signed_at
