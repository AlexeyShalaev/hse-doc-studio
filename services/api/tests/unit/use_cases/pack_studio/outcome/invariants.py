"""Связи внутри результата, которые схема выразить не может (те же, что держит тест контракта на эталонах):
ссылки `why` указывают на решения трассы, решения помнят свои элементы, `digest` равен телу."""

from __future__ import annotations

from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeResponse
from hse_doc_studio.core.pack_studio.outcome.model import Outcome
from hse_doc_studio.core.pack_studio.outcome.payload import to_json

SECTIONS = ["documents", "meta", "forms", "participants", "points", "route", "checks"]


def _why_lists(node: Any) -> list[list[str]]:
    found: list[list[str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "why":
                found.append(value)
            elif key != "trace":
                found.extend(_why_lists(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_why_lists(item))
    return found


def body_of(outcome: Outcome, *, state: str = "work_tree") -> dict[str, Any]:
    """Тело ответа контракта: результат плюс поля границы запроса."""
    return {
        "workspace_id": "6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10",
        "pack": "p",
        "template": "t",
        "version": "1.0.0",
        "state": state,
        **to_json(outcome),
    }


def assert_contract(outcome: Outcome) -> dict[str, Any]:
    """Результат принимают строгие модели контракта (лишние и недостающие поля отвергаются) и держатся связи."""
    body = body_of(outcome)
    PackOutcomeResponse.model_validate(body)
    assert_links(body)
    return body


def assert_links(body: dict[str, Any]) -> None:
    ids = [t["id"] for t in body["trace"]]
    assert len(ids) == len(set(ids))
    assert {i for why in _why_lists(body) for i in why} <= set(ids)
    assert {t["id"] for t in body["trace"] if not t["subjects"]} == set()

    subjects = {t["id"]: {(s["section"], s["id"]) for s in t["subjects"]} for t in body["trace"]}
    expected: list[tuple[tuple[str, str], list[str]]] = []
    expected += [(("documents", d["id"]), d["why"]) for d in body["documents"]]
    expected += [(("meta", f["id"]), f["why"]) for f in body["meta"]]
    for form in body["forms"]:
        expected.append((("forms", form["id"]), form["why"]))
        expected += [(("forms", f"{form['id']}/{f['id']}"), f["why"]) for f in form["fields"]]
    for point in body["points"]:
        expected += [(("points", f"{point['id']}/{i['doc_id']}"), i["why"]) for i in point["items"] if i["why"]]
        expected.append((("route", point["id"]), point["route"]["why"]))
    broken = {(element, i) for element, why in expected for i in why if element not in subjects[i]}
    # `why` пункта точки может ссылаться на решение самого документа: оно помнит документ, не пункт.
    assert all(element[0] == "points" and any(e[0] == "documents" for e in subjects[i]) for element, i in broken)

    digest = body["digest"]
    assert digest["documents"] == {d["id"]: d["state"] for d in body["documents"]}
    assert digest["participants"] == [p["persona"] for p in body["participants"] if p["present"]]
    assert digest["meta_visible"] == [f["id"] for f in body["meta"] if f["visible"]]
    assert [s["section"] for s in digest["sections"]] == SECTIONS
    for point, summary in zip(body["points"], digest["points"], strict=True):
        assert summary["items"] == [i["doc_id"] for i in point["items"] if i["active"]]
        assert summary["steps"] == [[p["persona"] for p in step] for step in point["route"]["steps"]]
        assert summary["pairs"] == len(point["route"]["pairs"])
    for doc in body["documents"]:
        assert (doc["state"] == "absent") == (not doc["instances"])
        assert (doc["state"] == "absent") == (doc["source_file"] is None)
        assert all(v["available"] for v in doc["variants"] if v["chosen"])
    for point in body["points"]:
        for item in point["items"]:
            assert (item["off_reason"] is None) == item["active"]
