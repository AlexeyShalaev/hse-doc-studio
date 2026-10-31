"""Сокет совместной правки на живом приложении: допуск по ролям, обмен правками, запись на диск, чужие правки."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.infra.collab import protocol as proto
from pycrdt import Doc, Text, create_sync_message, create_update_message, handle_sync_message
from starlette.websockets import WebSocketDisconnect

from tests.integration.api.review.conftest import NOTES, ORIGIN, TEXT, Person, Review, run_sql, set_member

pytestmark = pytest.mark.pg


class Peer:
    """Браузерная сторона: Y.Doc и открытый сокет."""

    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.doc = Doc()
        self.text: Text = self.doc.get("text", type=Text)
        self.events: list[dict[str, Any]] = []
        self.ws.send_bytes(create_sync_message(self.doc))

    def drain(self, until: Any = None, timeout: float = 5.0) -> None:
        """Читает кадры сервера, пока не выполнится `until` (или не кончится время)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if until is not None and until():
                return
            frame = self.ws.receive_bytes()
            if frame[0] == proto.MSG_SYNC:
                reply = handle_sync_message(frame[1:], self.doc)
                if reply is not None:
                    self.ws.send_bytes(reply)
            elif frame[0] == proto.MSG_EVENT:
                self.events.append(json.loads(frame[1:]))
            if until is None and self.events and str(self.text):
                return

    def forge(self, index: int, value: str) -> None:
        """Правка в обход редактора (он у читателя только для чтения): локальный документ не меняется."""
        other = Doc()
        other.apply_update(self.doc.get_update())
        text = other.get("text", type=Text)
        before = other.get_state()
        text.insert(index, value)
        self.ws.send_bytes(create_update_message(other.get_update(before)))

    def type(self, index: int, value: str) -> None:
        before = self.doc.get_state()
        self.text.insert(index, value)
        self.ws.send_bytes(create_update_message(self.doc.get_update(before)))


@contextmanager
def _open(review: Review, who: Person, path: str = NOTES, origin: str | None = ORIGIN):  # type: ignore[no-untyped-def]
    url = f"/api/collab/v1/projects/{review.project}/room?path={path}"
    headers = {"Origin": origin} if origin else {}
    with who as client, client.websocket_connect(url, headers=headers) as ws:
        yield Peer(ws)


def _file(review: Review) -> str:
    return review.world.anna.get(f"/api/v1/projects/{review.project}/files/{NOTES}").text


def _wait_for(check: Any, timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return False


def test__editors__type_together_and_file_on_disk_gets_both_edits(review: Review) -> None:
    with _open(review, review.world.anna) as anna, _open(review, review.world.vera) as vera:
        anna.drain(lambda: str(anna.text) == TEXT)
        vera.drain(lambda: str(vera.text) == TEXT)
        hello = next(e for e in anna.events if e["type"] == "hello")
        assert hello["can_write"] is True

        anna.type(0, "А: ")
        vera.drain(lambda: str(vera.text).startswith("А: "))
        vera.type(len(str(vera.text).encode()), "В: конец\n")
        anna.drain(lambda: str(anna.text).endswith("В: конец\n"))

        assert str(anna.text) == str(vera.text) == "А: " + TEXT + "В: конец\n"
        # Запись на диск идёт через общий путь сохранения; ждём отложенную запись комнаты.
        assert _wait_for(lambda: _file(review) == "А: " + TEXT + "В: конец\n")


def test__reviewer__reads_live_but_cannot_write(review: Review) -> None:
    with _open(review, review.world.anna) as anna, _open(review, review.rita) as rita:
        rita.drain(lambda: str(rita.text) == TEXT)
        assert next(e for e in rita.events if e["type"] == "hello")["can_write"] is False

        rita.forge(0, "ВЗЛОМ ")
        anna.drain(lambda: str(anna.text) == TEXT)
        anna.type(0, "Ок ")
        rita.drain(lambda: str(rita.text).startswith("Ок "))

        assert _wait_for(lambda: _file(review).startswith("Ок "))
        assert "ВЗЛОМ" not in _file(review)
        rita.drain(lambda: any(e["type"] == "read_only" for e in rita.events))


def test__outside_edit_is_merged_into_open_room(review: Review) -> None:
    with _open(review, review.world.anna) as anna:
        anna.drain(lambda: str(anna.text) == TEXT)

        review.world.vera.put(f"/api/v1/projects/{review.project}/files/{NOTES}", content=(TEXT + "Из git.\n").encode())

        anna.drain(lambda: str(anna.text).endswith("Из git.\n") and any(e["type"] == "external" for e in anna.events))
        assert str(anna.text) == TEXT + "Из git.\n"


@pytest.mark.parametrize(
    ("person", "code"),
    [("gleb", 4403), ("dina", 4404)],
)
def test__no_access__socket_closes_with_code(review: Review, person: str, code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as closed, _open(review, getattr(review.world, person)) as peer:
        peer.drain(timeout=3)

    assert closed.value.code == code


def test__anonymous_and_foreign_origin_are_refused(review: Review) -> None:
    with pytest.raises(WebSocketDisconnect) as anonymous, _open(review, review.world.anonymous()) as peer:
        peer.drain(timeout=3)
    assert anonymous.value.code == 4401

    with (
        pytest.raises(WebSocketDisconnect) as foreign,
        _open(review, review.world.anna, origin="http://evil.example") as peer,
    ):
        peer.drain(timeout=3)
    assert foreign.value.code in (1008, 1000)


def test__binary_or_missing_file_is_refused(review: Review) -> None:
    review.world.anna.put(f"/api/v1/projects/{review.project}/files/pic.png", content=b"\x89PNG\xff\xfe\x00")

    with pytest.raises(WebSocketDisconnect) as binary, _open(review, review.world.anna, "pic.png") as peer:
        peer.drain(timeout=3)
    assert binary.value.code == 4415

    with pytest.raises(WebSocketDisconnect) as missing, _open(review, review.world.anna, "net.tex") as peer:
        peer.drain(timeout=3)
    assert missing.value.code == 4415


def test__role_change_during_session__switches_to_read_then_revoke_closes_socket(
    review: Review, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.collab, "recheck_s", 0.3)
    vera_id = review.world.ids["vera"]

    def session() -> None:
        with _open(review, review.world.vera) as vera:
            vera.drain(lambda: str(vera.text) == TEXT)
            assert next(e for e in vera.events if e["type"] == "hello")["can_write"] is True

            set_member(review.project, vera_id, Role.reviewer)
            vera.drain(lambda: any(e["type"] == "role" and e["can_write"] is False for e in vera.events))

            run_sql("DELETE FROM project_members WHERE principal_id = :uid", uid=vera_id)
            vera.drain(timeout=6)

    with pytest.raises(WebSocketDisconnect) as closed:
        session()

    assert closed.value.code == 4403
