"""Выгрузка PDF локальной сборки на сервер: права, пределы, хранение последних версий и аудит."""

from __future__ import annotations

import hashlib

import pytest
from hse_doc_studio.api.config import settings

from tests.integration.api.git_remote.conftest import Live, Person

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _doc_id(live: Live, owner: Person, project: str) -> str:
    docs = live.call("GET", f"/api/v1/projects/{project}/documents", owner).json()
    return str(docs[0]["id"])


def _put(
    live: Live, project: str, doc: str, token: str, body: bytes = PDF, **params: str | int
) -> tuple[int, dict[str, object]]:
    params.setdefault("sha256", hashlib.sha256(body).hexdigest())
    response = live.call(
        "PUT",
        f"/git/-/projects/{project}/documents/{doc}/pdf",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/pdf"},
        content=body,
        params=params,
    )
    return response.status_code, response.json()


def _listed(live: Live, project: str, who: Person) -> list[dict[str, object]]:
    response = live.call("GET", f"/api/v1/projects/{project}/artifacts", who)
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def test__upload__owner_with_write_token__stored_listed_downloadable_and_audited(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:read", "git:write"], name="Студия на MacBook")

    status, body = _put(live, project, doc, token, name="Курсовая.pdf", pages=12, commit="a" * 40)

    assert status == 201
    artifact = body["artifact"]
    assert body["created"] is True
    assert artifact["size"] == len(PDF)
    assert artifact["pages"] == 12
    assert artifact["file_name"] == "Курсовая.pdf"
    assert artifact["uploaded_by_name"] == "anna"
    listed = _listed(live, project, anna)
    assert [item["id"] for item in listed] == [artifact["id"]]
    served = live.call("GET", artifact["file_url"], anna)
    assert served.status_code == 200
    assert served.content == PDF
    assert served.headers["content-type"] == "application/pdf"
    rows = live.sql("SELECT details FROM audit_log WHERE action = 'artifact.pdf_uploaded' AND target = :t", t=project)
    assert [r[0]["sha256"] for r in rows] == [hashlib.sha256(PDF).hexdigest()]
    assert rows[0][0]["doc_id"] == doc


def test__upload__same_file_twice__second_call_creates_nothing(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:write"])

    first = _put(live, project, doc, token)
    second = _put(live, project, doc, token)

    assert (first[0], second[0]) == (201, 200)
    assert second[1]["created"] is False
    assert second[1]["artifact"]["id"] == first[1]["artifact"]["id"]
    assert len(_listed(live, project, anna)) == 1


def test__upload__more_versions_than_kept__oldest_removed_with_their_objects(
    live: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.artifacts, "keep_per_document", 2)
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:write"])
    ids = [str(_put(live, project, doc, token, PDF + bytes([n]) * 4)[1]["artifact"]["id"]) for n in range(3)]  # type: ignore[index]

    listed = [item["id"] for item in _listed(live, project, anna)]

    assert listed == [ids[2], ids[1]]
    assert live.call("GET", f"/api/v1/projects/{project}/artifacts/{ids[0]}/file", anna).status_code == 404
    stored = list((live.tmp / "data").rglob("*.pdf"))
    assert len(stored) == 2


@pytest.mark.parametrize(
    ("body", "params", "expected_status", "expected_code"),
    [
        (b"hello world, not a pdf", {}, 415, "artifact_not_pdf"),
        (PDF, {"sha256": "0" * 64}, 422, "artifact_checksum_mismatch"),
    ],
)
def test__upload__bad_file__rejected_with_code_and_nothing_stored(
    live: Live, body: bytes, params: dict[str, str], expected_status: int, expected_code: str
) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:write"])

    status, reply = _put(live, project, doc, token, body, **params)

    assert (status, reply["code"]) == (expected_status, expected_code)
    assert _listed(live, project, anna) == []


def test__upload__over_limit__413_by_length_and_by_stream(live: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.artifacts, "max_pdf_bytes", len(PDF) - 1)
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:write"])

    status, reply = _put(live, project, doc, token)

    assert (status, reply["code"]) == (413, "artifact_too_large")
    assert _listed(live, project, anna) == []


def test__upload__unknown_document__404(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:write"])

    status, reply = _put(live, project, "no-such-doc", token)

    assert (status, reply["code"]) == (404, "artifact_unknown_document")


def test__upload__token_without_write_scope__403_and_no_token_401(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)

    read_only = _put(live, project, doc, live.token(anna, ["git:read"]))
    api_only = _put(live, project, doc, live.token(anna, ["api"]))
    anonymous = live.call("PUT", f"/git/-/projects/{project}/documents/{doc}/pdf", content=PDF)

    assert read_only[0] == 403
    assert api_only[0] == 403
    assert anonymous.status_code == 401
    assert _listed(live, project, anna) == []


def test__upload__roles__reader_and_stranger_cannot_but_reader_can_view(live: Live) -> None:
    anna, boris, vera, olga = (live.person(n) for n in ("anna", "boris", "vera", "olga"))
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    live.add_member(project, boris, "editor")
    live.add_member(project, vera, "reader", show_sources=False)

    editor = _put(live, project, doc, live.token(boris, ["git:write"]))
    reader = _put(live, project, doc, live.token(vera, ["git:write"]), PDF + b"1")
    stranger = _put(live, project, doc, live.token(olga, ["git:write"]), PDF + b"2")

    assert editor[0] == 201
    assert reader[0] == 403
    assert stranger[0] == 404
    seen = _listed(live, project, vera)
    assert [item["uploaded_by_name"] for item in seen] == ["boris"]
    assert live.call("GET", seen[0]["file_url"], vera).content == PDF
    assert live.call("GET", f"/api/v1/projects/{project}/artifacts", olga).status_code == 404


def test__upload__team_project__author_uploads_only_own_document(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    project = live.create_team_project(anna)
    docs = [d["id"] for d in live.call("GET", f"/api/v1/projects/{project}/documents", anna).json()]
    mine = next(d for d in docs if d.endswith("--anna-petrova") or "--" in d)
    slug = mine.split("--", 1)[1]
    other = next(d for d in docs if d.split("--", 1)[-1] != slug and "--" in d)
    live.add_member(project, boris, "editor", persona=slug)
    token = live.token(boris, ["git:write"])

    own = _put(live, project, mine, token)
    foreign = _put(live, project, other, token)

    assert own[0] == 201
    assert foreign[0] == 403


def test__delete__editor_removes_pdf_reader_cannot__audited(live: Live) -> None:
    anna, vera = live.person("anna"), live.person("vera")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    live.add_member(project, vera, "reader")
    artifact = _put(live, project, doc, live.token(anna, ["git:write"]))[1]["artifact"]
    url = f"/api/v1/projects/{project}/artifacts/{artifact['id']}"  # type: ignore[index]

    denied = live.call("DELETE", url, vera)
    removed = live.call("DELETE", url, anna)

    assert denied.status_code == 403
    assert removed.status_code == 204
    assert _listed(live, project, anna) == []
    assert live.call("DELETE", url, anna).status_code == 404
    rows = live.sql("SELECT 1 FROM audit_log WHERE action = 'artifact.deleted' AND target = :t", t=project)
    assert len(rows) == 1
