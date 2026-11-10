"""MCP облака: маршрут подписания (docs/design/signing-route.md, раздел 6.8).

Ход маршрута и свои задачи читаются, отправка это опасный тул с теми же проверками, что `POST .../send`
(помехи предпросмотра, отпечатки, право `SUBMISSION_CREATE`). Согласовать, подписать и вернуть на доработку через
MCP нельзя: таких тулов нет.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from hse_doc_studio.use_cases.mcp.catalog import MCP_TOOL_RULES
from hse_doc_studio.use_cases.signing_route import author as author_module

from tests.integration.api.mcp.server.test_mcp_server_pg import _call, _enable, _rpc, _token
from tests.integration.api.signing_routes.signer_stand import APPLICATION, PROPOSAL, Trio, make_trio
from tests.integration.api.signing_routes.stand import TOPIC, Person, Stand, make_project, person

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

_READ_TOOLS = {"get_signing_route", "list_signing_tasks"}
_SEND = "send_for_signing"


def _mcp(stand: Stand, who: Person) -> dict[str, str]:
    return _token(stand, who.email, ["mcp"])


def _names(stand: Stand, headers: dict[str, str]) -> set[str]:
    resp = _rpc(stand, headers, "tools/list")
    assert resp.status_code == 200, resp.text
    return {tool["name"] for tool in resp.json()["result"]["tools"]}


def _body(result: dict[str, Any]) -> Any:
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def _refused(result: dict[str, Any], code: str) -> str:
    assert result["isError"] is True, result
    assert result["_meta"]["code"] == code, result
    return str(result["content"][0]["text"])


def _audit(stand: Stand, action: str, project_id: str) -> list[dict[str, Any]]:
    items = stand.admin().get("/api/admin/audit", params={"action": action, "target": project_id}).json()["items"]
    return list(items)


def _states(route: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(p["persona"], p["state"], p["next_action"]) for step in route["steps"] for p in step]


# --- каталог ----------------------------------------------------------------------------------------------------------


async def test__tools_list__reading_is_offered__sending_only_when_the_admin_enables_it(stand: Stand) -> None:
    _enable(stand)
    headers = _mcp(stand, await person(stand, "Иванов Иван Иванович"))

    by_default = _names(stand, headers)
    _enable(stand, enabled_dangerous=[_SEND])
    enabled = _names(stand, headers)

    assert by_default >= _READ_TOOLS
    assert _SEND not in by_default
    assert _SEND in enabled


async def test__tools_list__no_tool_approves_signs_a_task_or_returns_a_route(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[r.name for r in MCP_TOOL_RULES if r.meta.dangerous])
    headers = _token(stand, (await person(stand, "Иванов Иван Иванович")).email, ["mcp", "sign"])

    tools = {t["name"]: t for t in _rpc(stand, headers, "tools/list").json()["result"]["tools"]}

    # Всё, что MCP умеет с маршрутом: прочитать и отправить. Решение подписанта остаётся в интерфейсе.
    route_tools = {name for name in tools if "signing" in name}
    assert route_tools == {*_READ_TOOLS, _SEND}
    assert not [name for name in tools if "approve" in name or "return" in name or "task" in name.split("_")]
    assert tools[_SEND]["annotations"]["destructiveHint"] is True
    assert tools["get_signing_route"]["annotations"]["readOnlyHint"] is True
    assert tools[_SEND]["inputSchema"]["required"] == ["project_id", "profile_id"]
    assert set(tools[_SEND]["inputSchema"]["properties"]) == {"project_id", "profile_id"}


# --- чтение -----------------------------------------------------------------------------------------------------------


async def test__get_signing_route__progress_of_the_checkpoint_route(stand: Stand) -> None:
    _enable(stand)
    trio = await make_trio(stand, academic="none")
    trio.sent()
    headers = _mcp(stand, trio.author)
    args = {"project_id": trio.project.id}

    route = _body(_call(stand, headers, "get_signing_route", {**args, "profile_id": TOPIC}))["route"]
    listed = _body(_call(stand, headers, "get_signing_route", args))["routes"]

    assert (route["route_id"], route["status"], route["phase"], route["round"]) == (
        trio.route_id,
        "active",
        "approval",
        1,
    )
    assert (route["current_step"], route["steps_total"], route["stop_reason"]) == (2, 2, None)
    assert route["sent_by"] == "Иванов Иван Иванович"
    assert _states(route) == [("author", "done", "done"), ("supervisor", "to_approve", "approve")]
    assert route["waiting_for"] == [
        {
            "name": "Петров Пётр Петрович",
            "persona": "supervisor",
            "step": 2,
            "state": "to_approve",
            "next_action": "approve",
        }
    ]
    assert [d["doc_id"] for d in route["docs"]] == [PROPOSAL, APPLICATION]
    assert [e["kind"] for e in route["events"]] == ["sent", "approved"]
    assert route["signing_page"] == f"/sign/{trio.project.id}/{trio.route_id}"
    assert [(r["route_id"], r["status"], r["current_step"]) for r in listed] == [(trio.route_id, "active", 2)]
    assert listed[0]["waiting_for"] == [{"name": "Петров Пётр Петрович", "persona": "supervisor"}]


async def test__get_signing_route__returned__stop_reason_who_and_comment_for_those_in_the_route(stand: Stand) -> None:
    _enable(stand)
    trio = await make_trio(stand, academic="none")
    trio.sent()
    assert trio.give_back(trio.supervisor, "Уточните цель проекта").status_code == 200
    outsider = await person(stand, "Читатель")
    await trio.project.member(outsider, "reader", None)
    args = {"project_id": trio.project.id, "profile_id": TOPIC}

    mine = _body(_call(stand, _mcp(stand, trio.author), "get_signing_route", args))["route"]
    theirs = _body(_call(stand, _mcp(stand, outsider), "get_signing_route", args))["route"]

    assert (mine["status"], mine["stop_reason"], mine["waiting_for"]) == ("returned", "returned", [])
    assert mine["stopped_by"] == {"name": "Петров Пётр Петрович", "persona": "supervisor"}
    assert [(e["kind"], e["comment"]) for e in mine["events"]][-1] == ("returned", "Уточните цель проекта")
    # Читатель проекта видит ход, но не комментарий возврата (раздел 7).
    assert (theirs["status"], theirs["stop_reason"]) == ("returned", "returned")
    assert [e["comment"] for e in theirs["events"]] == [None, None, None]


async def test__get_signing_route__checkpoint_without_a_route__says_so(stand: Stand) -> None:
    _enable(stand)
    author = await person(stand, "Иванов Иван Иванович")
    project = make_project(stand, author)

    body = _body(
        _call(stand, _mcp(stand, author), "get_signing_route", {"project_id": project.id, "profile_id": TOPIC})
    )

    assert body["route"] is None
    assert "send_for_signing" in body["hint"]


async def test__get_signing_route__stranger__project_not_found(stand: Stand) -> None:
    _enable(stand)
    trio = await make_trio(stand, academic="none")
    stranger = await person(stand, "Чужой")

    result = _call(stand, _mcp(stand, stranger), "get_signing_route", {"project_id": trio.project.id})

    _refused(result, "not_found")


async def test__list_signing_tasks__only_where_my_action_is_needed_now(stand: Stand) -> None:
    _enable(stand)
    trio = await make_trio(stand)
    trio.sent()

    author = _body(_call(stand, _mcp(stand, trio.author), "list_signing_tasks", {}))["tasks"]
    supervisor = _body(_call(stand, _mcp(stand, trio.supervisor), "list_signing_tasks", {}))["tasks"]
    academic = _body(_call(stand, _mcp(stand, trio.academic), "list_signing_tasks", {}))["tasks"]

    assert author == []
    assert academic == []
    [task] = supervisor
    assert task["project"] == {"id": trio.project.id, "name": "КП: маршрут"}
    assert (task["route_id"], task["profile"]["id"], task["round"]) == (trio.route_id, TOPIC, 1)
    assert (task["sender"], task["next_action"], task["deadline"]) == ("Иванов Иван Иванович", "approve", None)
    assert task["signing_page"] == f"/sign/{trio.project.id}/{trio.route_id}"


# --- отправка ---------------------------------------------------------------------------------------------------------


async def test__send_for_signing__off_by_default(stand: Stand) -> None:
    _enable(stand)
    trio = await make_trio(stand, academic="none")
    args = {"project_id": trio.project.id, "profile_id": TOPIC}

    result = _call(stand, _mcp(stand, trio.author), _SEND, args)

    _refused(result, "tool_disabled")
    assert trio.route()["status"] == "draft"


async def test__send_for_signing__sends_the_saved_route_like_the_button(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    trio = await make_trio(stand, academic="none")
    headers = _mcp(stand, trio.author)
    args = {"project_id": trio.project.id, "profile_id": TOPIC}

    sent = _body(_call(stand, headers, _SEND, args))

    assert sent["sent"] is True
    route = sent["route"]
    assert (route["route_id"], route["status"], route["round"]) == (trio.route_id, "active", 1)
    # Отправитель участник первого шага: отправка это его согласование; дальше очередь научрука.
    assert _states(route) == [("author", "done", "done"), ("supervisor", "to_approve", "approve")]
    assert trio.events() == ["sent", "approved"]
    assert trio.withheld() == {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}
    tasks = _body(_call(stand, _mcp(stand, trio.supervisor), "list_signing_tasks", {}))["tasks"]
    assert [t["route_id"] for t in tasks] == [trio.route_id]
    # В журнале аудита отправка от имени владельца токена и вызов тула.
    [send] = _audit(stand, "signing_route.send", trio.project.id)
    assert (send["actor_id"], send["details"]["route_id"]) == (trio.author.id, trio.route_id)
    calls = stand.admin().get("/api/admin/audit", params={"action": "mcp.call", "target": _SEND}).json()["items"]
    assert [
        (c["actor_id"], c["details"]["outcome"]) for c in calls if c["details"]["project_id"] == trio.project.id
    ] == [(trio.author.id, "ok")]

    again = _call(stand, headers, _SEND, args)

    assert "уже отправлен" in _refused(again, "failed")
    assert trio.events() == ["sent", "approved"]


async def test__send_for_signing__no_route_yet__draft_from_the_pack_is_sent(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(stand, author, supervisor={"name": "Петров Пётр Петрович", "role": "university"})
    await project.member(supervisor, "reviewer", "supervisor")
    for doc_id in (PROPOSAL, APPLICATION):
        project.build(doc_id)
    project.png(author, "author")
    project.place(author)

    sent = _body(_call(stand, _mcp(stand, author), _SEND, {"project_id": project.id, "profile_id": TOPIC}))

    assert sent["route"]["status"] == "active"
    assert _states(sent["route"]) == [("author", "done", "done"), ("supervisor", "to_approve", "approve")]
    assert [a["action"] for a in _audit(stand, "signing_route.create", project.id)] == ["signing_route.create"]


async def test__send_for_signing__blockers__listed_and_nothing_is_sent(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    author = await person(stand, "Иванов Иван Иванович")
    project = make_project(stand, author, supervisor={"name": "Петров Пётр Петрович", "role": "university"})
    project.build(APPLICATION)
    args = {"project_id": project.id, "profile_id": TOPIC}

    text = _refused(_call(stand, _mcp(stand, author), _SEND, args), "failed")

    assert text.startswith("Маршрут не отправлен:")
    assert f"документ {PROPOSAL} не собран" in text
    assert f"документ {APPLICATION} не собран" not in text
    assert "нет человека с персоной supervisor" in text
    assert "ваша подпись не готова" in text
    routes = project.call(author, "GET", project.routes).json()["items"]
    assert [r["status"] for r in routes] == ["draft"]
    assert _audit(stand, "signing_route.send", project.id) == []


async def test__send_for_signing__invited_signer_has_not_joined__not_sent(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(stand, author, supervisor={"name": "Петров Пётр Петрович", "role": "university"})
    for doc_id in (PROPOSAL, APPLICATION):
        project.build(doc_id)
    project.png(author, "author")
    invited = project.call(
        author,
        "POST",
        f"{project.base}/invitations",
        json={"email": supervisor.email, "role": "reviewer", "persona": "supervisor"},
    )
    assert invited.status_code == 201, invited.text
    args = {"project_id": project.id, "profile_id": TOPIC}

    text = _refused(_call(stand, _mcp(stand, author), _SEND, args), "failed")

    # API такой маршрут отправил бы (приглашённый ждёт в нём), MCP отправляет только готовый состав (раздел 6.8).
    assert "приглашение в проект ещё не принято" in text
    assert [r["status"] for r in project.call(author, "GET", project.routes).json()["items"]] == ["draft"]


async def test__send_for_signing__reviewer__forbidden(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    trio = await make_trio(stand, academic="none")
    args = {"project_id": trio.project.id, "profile_id": TOPIC}

    result = _call(stand, _mcp(stand, trio.supervisor), _SEND, args)

    _refused(result, "forbidden")
    assert trio.route()["status"] == "draft"


async def test__send_for_signing__unknown_checkpoint__not_found(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    trio = await make_trio(stand, academic="none")

    result = _call(stand, _mcp(stand, trio.author), _SEND, {"project_id": trio.project.id, "profile_id": "nope"})

    _refused(result, "not_found")


async def test__send_for_signing__returned_route__resend_not_more_often_than_once_a_minute(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    trio: Trio = await make_trio(stand, academic="none")
    headers = _mcp(stand, trio.author)
    args = {"project_id": trio.project.id, "profile_id": TOPIC}
    _body(_call(stand, headers, _SEND, args))
    assert trio.give_back(trio.supervisor).status_code == 200

    too_soon = _call(stand, headers, _SEND, args)
    monkeypatch.setattr(author_module, "SEND_INTERVAL", timedelta(0))
    resent = _body(_call(stand, headers, _SEND, args))

    assert "меньше минуты" in _refused(too_soon, "rate_limited")
    assert (resent["route"]["route_id"], resent["route"]["status"], resent["route"]["round"]) == (
        trio.route_id,
        "active",
        2,
    )
    assert trio.events() == ["sent", "approved", "returned", "sent", "approved"]
