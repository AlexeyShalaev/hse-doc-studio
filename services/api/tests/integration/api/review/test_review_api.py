"""Ревью-комментарии на живом приложении: права по ролям, треды и ответы, упоминания, «Входящие», события."""

from __future__ import annotations

import pytest

from tests.integration.api.review.conftest import NOTES, Review

pytestmark = pytest.mark.pg


def test__reviewer__creates_thread_and_editors_get_inbox_notification(review: Review) -> None:
    thread = review.create(review.rita, "Уточните термин")

    assert thread["status"] == "open"
    assert thread["path"] == NOTES
    assert thread["created_by_name"] == "Рита"
    assert [c["body"] for c in thread["comments"]] == ["Уточните термин"]  # type: ignore[index]
    for owner_or_editor in (review.world.anna, review.world.boris, review.world.vera):
        [note] = review.inbox(owner_or_editor, "review_thread")
        assert note["payload"]["path"] == NOTES  # type: ignore[index]
        assert note["payload"]["actor_name"] == "Рита"  # type: ignore[index]
        assert note["payload"]["excerpt"] == "Уточните термин"  # type: ignore[index]
        assert note["payload"]["ref_id"] == thread["id"]  # type: ignore[index]
    assert review.inbox(review.rita) == []


def test__list_threads__filtered_by_path_and_status(review: Review) -> None:
    thread = review.create(review.rita)

    listed = review.world.anna.get(f"{review.base}/threads", params={"path": NOTES}).json()["items"]
    assert [t["id"] for t in listed] == [thread["id"]]
    assert review.world.anna.get(f"{review.base}/threads", params={"status": "resolved"}).json()["items"] == []
    assert review.world.anna.get(f"{review.base}/threads", params={"path": "other.tex"}).json()["items"] == []


@pytest.mark.parametrize(("person", "status"), [("gleb", 403), ("dina", 404)])
def test__no_source_access__cannot_read_threads(review: Review, person: str, status: int) -> None:
    review.create(review.rita)

    response = getattr(review.world, person).get(f"{review.base}/threads")

    assert response.status_code == status


def test__reader_and_stranger__cannot_comment(review: Review) -> None:
    payload = {"path": NOTES, "anchor": review.anchor(), "body": "Можно?"}

    assert review.world.gleb.post(f"{review.base}/threads", json=payload).status_code == 403
    assert review.world.dina.post(f"{review.base}/threads", json=payload).status_code == 404


def test__editor__can_comment_too(review: Review) -> None:
    thread = review.create(review.world.vera, "Правка от редактора")

    assert thread["created_by_name"] == "Вера Смирнова"


def test__reply__notifies_participants_and_mention_goes_only_to_project_people(review: Review) -> None:
    thread = review.create(review.rita)
    anna_id = review.world.ids["anna"]
    dina_id = review.world.ids["dina"]

    replied = review.world.anna.post(
        f"{review.base}/threads/{thread['id']}/comments",
        json={"body": "Поправлю, @Борис посмотри и @Дина", "mentions": [review.world.ids["boris"], dina_id]},
    )

    assert replied.status_code == 201, replied.text
    comments = replied.json()["comments"]
    assert len(comments) == 2
    assert comments[1]["mentions"] == [review.world.ids["boris"]]
    [reply_note] = review.inbox(review.rita, "review_reply")
    assert reply_note["payload"]["actor_name"] == "Анна Петрова"
    [mention] = review.inbox(review.world.boris, "review_mention")
    assert mention["payload"]["ref_id"] == thread["id"]
    assert review.inbox(review.world.dina) == []
    assert review.inbox(review.world.anna, "review_reply") == []
    assert anna_id not in comments[1]["mentions"]


def test__mention_of_user_without_source_access_is_dropped(review: Review) -> None:
    thread = review.create(review.rita)

    replied = review.world.anna.post(
        f"{review.base}/threads/{thread['id']}/comments",
        json={"body": "@Глеб", "mentions": [review.world.ids["gleb"]]},
    )

    assert replied.json()["comments"][1]["mentions"] == []
    assert review.inbox(review.world.gleb) == []


def test__mention_candidates__are_project_people_without_self(review: Review) -> None:
    found = review.rita.get(f"{review.base}/mentions", params={"q": "Вер"}).json()["items"]

    assert [c["name"] for c in found] == ["Вера Смирнова"]
    everyone = {c["name"] for c in review.rita.get(f"{review.base}/mentions").json()["items"]}
    assert "Рита" not in everyone
    assert review.world.gleb.get(f"{review.base}/mentions").status_code == 403


def test__status__author_or_editor_can_resolve_and_reopen(review: Review) -> None:
    mine = review.create(review.rita)
    other = review.world.vera.post(
        f"{review.base}/threads", json={"path": NOTES, "anchor": review.anchor("Заключение"), "body": "Чужой"}
    ).json()

    own = review.rita.put(f"{review.base}/threads/{mine['id']}/status", json={"status": "resolved"})
    foreign = review.rita.put(f"{review.base}/threads/{other['id']}/status", json={"status": "resolved"})
    by_editor = review.world.anna.put(f"{review.base}/threads/{other['id']}/status", json={"status": "resolved"})

    assert own.status_code == 200
    assert own.json()["status"] == "resolved"
    assert own.json()["resolved_by_name"] == "Рита"
    assert foreign.status_code == 403
    assert by_editor.status_code == 200
    [note] = review.inbox(review.world.vera, "review_resolved")
    assert note["payload"]["outcome"] == "resolved"
    reopened = review.rita.put(f"{review.base}/threads/{mine['id']}/status", json={"status": "open"})
    assert reopened.json()["status"] == "open"
    assert reopened.json()["resolved_at"] is None


def test__comment__only_author_edits_and_owner_or_author_deletes(review: Review) -> None:
    thread = review.create(review.rita)
    reply = review.world.anna.post(f"{review.base}/threads/{thread['id']}/comments", json={"body": "Ответ"}).json()[
        "comments"
    ][1]
    root = thread["comments"][0]  # type: ignore[index]

    assert review.rita.patch(f"{review.base}/comments/{reply['id']}", json={"body": "Взлом"}).status_code == 403
    edited = review.world.anna.patch(f"{review.base}/comments/{reply['id']}", json={"body": "Ответ 2"})
    assert edited.status_code == 200
    assert edited.json()["comments"][1]["body"] == "Ответ 2"
    assert edited.json()["comments"][1]["edited_at"] is not None
    assert review.world.vera.delete(f"{review.base}/comments/{reply['id']}").status_code == 403
    # Рита не уносит корень, под которым ответила Анна, а Анна как владелец может.
    assert review.rita.delete(f"{review.base}/comments/{root['id']}").status_code == 409
    assert review.world.anna.delete(f"{review.base}/comments/{reply['id']}").status_code == 204
    assert review.rita.delete(f"{review.base}/comments/{root['id']}").status_code == 204
    assert review.world.anna.get(f"{review.base}/threads").json()["items"] == []


def test__validation__empty_body_stale_anchor_and_missing_file(review: Review) -> None:
    anchor = review.anchor()
    url = f"{review.base}/threads"

    assert review.rita.post(url, json={"path": NOTES, "anchor": anchor, "body": "   "}).status_code == 422
    stale = review.rita.post(url, json={"path": NOTES, "anchor": {**anchor, "quote": "нет такого"}, "body": "x"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "anchor_stale"
    empty = review.rita.post(url, json={"path": NOTES, "anchor": {**anchor, "quote": " "}, "body": "x"})
    assert empty.json()["code"] == "empty_quote"
    assert review.rita.post(url, json={"path": "нет.tex", "anchor": anchor, "body": "x"}).status_code == 404


def test__thread_survives_file_edits_because_server_keeps_quote_and_context(review: Review) -> None:
    thread = review.create(review.rita)

    review.world.anna.put(
        f"/api/v1/projects/{review.project}/files/{NOTES}", content=("Новый абзац.\n" + "\n" * 3).encode()
    )
    listed = review.rita.get(f"{review.base}/threads", params={"path": NOTES}).json()["items"]

    assert listed[0]["id"] == thread["id"]
    assert listed[0]["anchor"]["quote"] == "совместную правку"
