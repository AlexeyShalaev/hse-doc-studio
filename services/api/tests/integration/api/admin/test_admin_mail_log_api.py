"""`/api/admin/mail-log` (docs/design/mail-log.md, 6, срез B6): ответы совпадают с эталонами B1, права, коды 6.3,
`no-store` и ни одного токена или исходной ссылки ни в одном ответе."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.api.schemas.admin import encode_cursor
from hse_doc_studio.api.schemas.mail_log import (
    AdminMailLogDetail,
    AdminMailLogEntry,
    AdminMailLogPage,
    AdminMailLogResendBatch,
    AdminMailLogResendResult,
    AdminMailLogSummary,
)
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.entities import ActorCredentials, TokenScope
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.lifecycle.policies import POLICY_BY_KEY
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.catalog import catalog
from hse_doc_studio.core.mail.compose import fixed_path
from hse_doc_studio.core.mail.journal import (
    SAFE_VALUES,
    MailCause,
    MailLinkKind,
    MailLogEntry,
    MailLogPage,
    MailLogQuery,
    MailOrigin,
    MailParams,
    MailRequest,
    MailStatus,
    safe_params,
    template_digest,
)
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.mail.dispatch import MailCounters, MailDispatcher
from hse_doc_studio.use_cases.mail.log import GetMailLogEntryUC, ListMailLogUC, MailLogSummaryUC
from hse_doc_studio.use_cases.mail.resend import ResendGate, ResendMailBatchUC, ResendMailUC, drain_resend_batches
from httpx import ASGITransport, AsyncClient

from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.mail_log import InMemoryMailLogRepository
from tests.fakes.mail_log_names import InMemoryMailLogNames
from tests.fakes.mail_relevance import InMemoryMailRelevance

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
_SERVER = "https://studio.example.org"
_SIGN = "/sign/5b0c1d2e-3f40-4152-8364-758697a8b9c0/0d1e2f30-4152-4637-8899-aabbccddeeff"
_PROJECT = "5b0c1d2e-3f40-4152-8364-758697a8b9c0"
_ADMIN = {"Authorization": "Bearer admin"}
_ANNA = ("c3d4a1f0e6b24d89a5f7120b9e8c6a31", "Анна Петрова", "anna.petrova@example.org")

# Безопасные параметры строк эталонов: из них карточка перерисовывает письмо (B1 снял тексты с настоящего письма).
_PARAMS: dict[int, MailParams] = {
    1207: MailParams(link=MailLinkKind.token, ttl_s=3600, server=_SERVER),
    1206: MailParams(
        link=MailLinkKind.page,
        link_path=_SIGN,
        server=_SERVER,
        values={
            "actor": "Анна Петрова",
            "project": "Курсовая работа по ГОСТ",
            "profile": "Заявка на тему КП (SmartLMS)",
            "deadline": "15.11.2026, 23:59 (МСК)",
        },
    ),
    1205: MailParams(
        link=MailLinkKind.token,
        expires_at=datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
        note_len=58,
        server=_SERVER,
        values={"actor": "Анна Петрова", "project": "Курсовая работа по ГОСТ", "role": "editor"},
    ),
    1204: MailParams(
        link=MailLinkKind.page,
        link_path=_SIGN,
        server=_SERVER,
        values={
            "actor": "Anna Petrova",
            "project": "Coursework draft",
            "profile": "Course project topic application (SmartLMS)",
            "deadline": "15 Nov 2026, 23:59 (Moscow time)",
        },
    ),
    **dict.fromkeys(
        # Версия 2 (раздел 14): ждёт автоповтора, исходная строка ручного повтора и сам повтор.
        (1300, 1301, 1302),
        MailParams(
            link=MailLinkKind.page,
            link_path=_SIGN,
            server=_SERVER,
            values={
                "actor": "Anna Petrova",
                "project": "Coursework draft",
                "profile": "Course project topic application (SmartLMS)",
                "deadline": "15 Nov 2026, 23:59 (Moscow time)",
            },
        ),
    ),
    1203: MailParams(
        link=MailLinkKind.page,
        link_path="/inbox",
        server=_SERVER,
        values={"actor": "Анна Петрова", "project": "Курсовая работа по ГОСТ", "role": "editor"},
    ),
    1202: MailParams(link=MailLinkKind.token, ttl_s=7 * 86400, server=_SERVER, values={"inviter": "Анна Петрова"}),
    1188: MailParams(link=MailLinkKind.token, ttl_s=2 * 86400, server=_SERVER),
    1101: MailParams(link=MailLinkKind.page, link_path="/inbox", server=_SERVER, values={"project": "Черновик"}),
    1042: MailParams(server=_SERVER),
}
# Строка 1188 ушла по прежнему шаблону: отпечаток не совпадает с текущим.
_OLD_DIGEST = "0123456789abcdef"
# Строки эталонов версии 2: в эталоны страниц B1 они не входят.
_V2_ROWS = frozenset({1300, 1301, 1302})


def _load(kind: str) -> dict[str, Any]:
    files = sorted((_FIXTURES / kind).glob("*.json"))
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in files}


def _fixture_rows() -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for data in _load("AdminMailLogPage").values():
        rows.update({item["id"]: item for item in data["items"]})
    rows.update({data["id"]: data for data in _load("AdminMailLogEntry").values()})
    rows.update({data["entry"]["id"]: data["entry"] for data in _load("AdminMailLogDetail").values()})
    return rows


def _entry(row: dict[str, Any]) -> MailLogEntry:
    """Строка журнала, которая должна дать ровно эту строку эталона."""
    template = MailTemplate(row["template"]) if row["template"] in set(MailTemplate) else None
    digest = template_digest(template, Lang(row["lang"])) if template is not None else "ffffffffffffffff"
    failure = row["failure"] or {}
    return MailLogEntry(
        id=row["id"],
        at=datetime.fromisoformat(row["at"]),
        duration_ms=row["duration_ms"],
        template=row["template"],
        lang=row["lang"],
        to_email=row["to_email"],
        to_user_id=row["to_user"]["id"] if row["to_user"] else None,
        subject=row["subject"],
        status=MailStatus(row["status"]),
        reason=row["reason"],
        smtp_code=failure.get("smtp_code"),
        error_text=failure.get("text"),
        message_id=row["message_id"],
        attempts=row["attempts"],
        cause=MailCause(row["cause"]),
        actor_user_id=row["actor"]["id"] if row["actor"] else None,
        task=row["task"],
        origin=row["origin"],
        request_id="req-1",
        project_id=row["project"]["id"] if row["project"] else None,
        ref_kind=row["ref"]["kind"] if row["ref"] else None,
        ref_id=row["ref"]["id"] if row["ref"] else None,
        params=_PARAMS[row["id"]],
        template_digest=_OLD_DIGEST if row["id"] == 1188 else digest,
        next_attempt_at=_moment(row["next_attempt_at"]),
        last_attempt_at=_moment(row["last_attempt_at"]),
        resent_from_id=row["resent_from_id"],
    )


def _moment(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class _EstimatedLog(InMemoryMailLogRepository):
    """Оценка числа строк без фильтров берётся из «статистики таблицы», как `reltuples` на Postgres."""

    def __init__(self) -> None:
        super().__init__()
        self.estimate: int | None = None

    async def page(self, query: MailLogQuery) -> MailLogPage:
        page = await super().page(query)
        return replace(page, total_estimate=self.estimate) if page.total_estimate is not None else page


class _Sender:
    def __init__(self) -> None:
        self.enabled = True
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        self.sent.append((to, subject))
        return f"<{len(self.sent)}@studio.example.org>"


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None]] = []

    async def record(
        self, action: str, *, actor_id: str | None, target: str | None = None, details: Any = None
    ) -> None:
        self.events.append((action, target))


class _Resolver:
    """Актор по токену в заголовке: админ сессией, админ токеном доступа, обычный человек."""

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        if credentials.bearer_token == "admin":
            return Actor.user("boss", "Иван Босс", is_instance_admin=True, source=ActorSource.session)
        if credentials.bearer_token == "admin-pat":
            return Actor.user(
                "boss", is_instance_admin=True, source=ActorSource.pat, scopes=frozenset({TokenScope.api.value})
            )
        if credentials.bearer_token == "user":
            return Actor.user("anna", "Анна", source=ActorSource.session)
        return None


@dataclass
class _Env:
    log: _EstimatedLog = field(default_factory=_EstimatedLog)
    names: InMemoryMailLogNames = field(default_factory=InMemoryMailLogNames)
    sender: _Sender = field(default_factory=_Sender)
    settings: InMemoryInstanceSettingsRepository = field(default_factory=InMemoryInstanceSettingsRepository)
    relevance: InMemoryMailRelevance = field(default_factory=InMemoryMailRelevance)
    audit: _Audit = field(default_factory=lambda: _Audit())
    client: AsyncClient | None = None

    def seed_fixtures(self, *, v2: bool = True) -> None:
        rows = _fixture_rows()
        self.log.entries = [_entry(rows[i]) for i in sorted(rows) if v2 or i not in _V2_ROWS]
        self.log.estimate = 1207
        for row in rows.values():
            for person in (row["to_user"], row["actor"]):
                if person:
                    self.names.add_person(person["id"], person["name"], person["email"])
        self.names.project_names[_PROJECT] = "Курсовая работа по ГОСТ"

    async def get(self, path: str, headers: dict[str, str] | None = None) -> Any:
        assert self.client is not None
        return await self.client.get(path, headers=_ADMIN if headers is None else headers)


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, env: _Env) -> None:
        super().__init__()
        self.e = env

    @provide
    def resolver(self) -> IActorResolver:
        return _Resolver()

    @provide
    def list_uc(self) -> ListMailLogUC:
        return ListMailLogUC(self.e.log, self.e.names)

    @provide
    def entry_uc(self) -> GetMailLogEntryUC:
        return GetMailLogEntryUC(self.e.log, self.e.names, self.gate())

    def gate(self) -> ResendGate:
        dispatcher = MailDispatcher(self.e.sender, self.e.log, counters=MailCounters(), clock=lambda: NOW)  # type: ignore[arg-type]
        return ResendGate(self.e.log, self.e.relevance, dispatcher, clock=lambda: NOW)

    @provide
    def resend_uc(self) -> ResendMailUC:
        dispatcher = MailDispatcher(self.e.sender, self.e.log, counters=MailCounters(), clock=lambda: NOW)  # type: ignore[arg-type]
        return ResendMailUC(self.e.log, self.gate(), dispatcher, self.e.audit, public_url=_SERVER)  # type: ignore[arg-type]

    @provide
    def resend_batch_uc(self) -> ResendMailBatchUC:
        dispatcher = MailDispatcher(self.e.sender, self.e.log, counters=MailCounters(), clock=lambda: NOW)  # type: ignore[arg-type]
        return ResendMailBatchUC(
            self.e.log,
            self.gate(),
            dispatcher,
            self.e.audit,
            public_url=_SERVER,
            clock=lambda: NOW,  # type: ignore[arg-type]
        )

    @provide
    def summary_uc(self) -> MailLogSummaryUC:
        return MailLogSummaryUC(self.e.log, self.e.sender, self.e.settings, clock=lambda: NOW)


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    e = _Env()
    app = FastAPI()
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    container = make_async_container(_Provider(e), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test"
    ) as client:
        e.client = client
        yield e
    await container.close()


def _without_html(detail: dict[str, Any]) -> dict[str, Any]:
    """HTML превью в эталонах короткий (6.2): форма та же, полное письмо даёт сервер."""
    preview = detail["preview"]
    return {**detail, "preview": {**preview, "html": None} if preview else None}


# --- эталоны B1 ---


@pytest.mark.parametrize(
    ("variant", "query"),
    [
        ("day", "limit=6"),
        ("next_page", f"limit=6&cursor={encode_cursor(1202)}"),
        ("filtered_failed", "status=failed"),
    ],
)
async def test__page__matches_the_fixture(env: _Env, variant: str, query: str) -> None:
    env.seed_fixtures(v2=False)

    response = await env.get(f"/api/admin/mail-log?{query}")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == _load("AdminMailLogPage")[variant]
    AdminMailLogPage.model_validate(response.json())


async def test__page__empty_log_matches_the_fixture(env: _Env) -> None:
    env.log.estimate = 0

    response = await env.get("/api/admin/mail-log")

    assert response.json() == _load("AdminMailLogPage")["empty"]


@pytest.mark.parametrize("variant", sorted(_load("AdminMailLogEntry")))
async def test__entry__matches_the_fixture(env: _Env, variant: str) -> None:
    env.seed_fixtures()
    expected = _load("AdminMailLogEntry")[variant]

    response = await env.get(f"/api/admin/mail-log/{expected['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["entry"] == expected
    AdminMailLogEntry.model_validate(response.json()["entry"])


@pytest.mark.parametrize("variant", sorted(_load("AdminMailLogDetail")))
async def test__detail__matches_the_fixture_with_the_full_mail(env: _Env, variant: str) -> None:
    env.seed_fixtures()
    expected = _load("AdminMailLogDetail")[variant]

    response = await env.get(f"/api/admin/mail-log/{expected['entry']['id']}")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    AdminMailLogDetail.model_validate(body)
    assert _without_html(body) == _without_html(expected)
    preview = body["preview"]
    if preview is None:
        return
    html = preview["html"]
    assert html.startswith("<!DOCTYPE html>")
    assert f"<title>{preview['subject']}</title>" in html
    # Единственная ссылка письма из журнала это адрес установки в подвале.
    assert html.count("href=") == 1
    assert f'href="{_SERVER}"' in html
    hidden = "[ссылка скрыта]" if body["entry"]["lang"] == "ru" else "[link hidden]"
    assert (hidden in html) is body["link_hidden"]
    note = "[сообщение не хранится в журнале]"
    assert (note in html) is body["note_hidden"]


@pytest.mark.parametrize("variant", sorted(_load("AdminMailLogSummary")))
async def test__summary__matches_the_fixture(env: _Env, variant: str) -> None:
    expected = _load("AdminMailLogSummary")[variant]
    rows = [
        _entry(row)
        for row in _fixture_rows().values()
        if row["status"] != "failed" and row["template"] != "weekly_digest"
    ]
    sample = {MailStatus(r.status): r for r in rows}
    sample[MailStatus.failed] = _entry(_fixture_rows()[1205])
    entries: list[MailLogEntry] = []
    for status in MailStatus:
        # Внутри окна, но раньше последнего сбоя эталона.
        entries += [replace(sample[status], at=NOW - timedelta(hours=23)) for _ in range(expected[status.value])]
    if expected["last_failure"]:
        last = datetime.fromisoformat(expected["last_failure"]["at"])
        entries.append(replace(sample[MailStatus.failed], at=last, reason=expected["last_failure"]["reason"]))
        entries.pop(next(i for i, e in enumerate(entries) if e.status is MailStatus.failed))
    # Ждут автоповтора: в `failed` не входят (V13).
    entries += [
        replace(sample[MailStatus.failed], at=NOW - timedelta(hours=23), next_attempt_at=NOW + timedelta(minutes=1))
        for _ in range(expected["retrying"])
    ]
    # Строки старше суток в сводку не входят.
    entries.append(replace(sample[MailStatus.failed], at=NOW - timedelta(hours=25)))
    for entry in sorted(entries, key=lambda e: e.at):
        await env.log.add(entry)
    env.sender.enabled = expected["smtp_configured"]
    if expected["retention_days"] != 90:
        key = POLICY_BY_KEY["mail_log"].setting_key
        assert key is not None
        await env.settings.set(key, expected["retention_days"], source="admin")

    response = await env.get("/api/admin/mail-log/summary")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == expected
    AdminMailLogSummary.model_validate(response.json())


# --- фильтры, курсор, имена ---


async def test__page__filters_combine_and_the_cursor_walks_the_whole_log(env: _Env) -> None:
    env.seed_fixtures(v2=False)

    async def ids(query: str) -> list[int]:
        response = await env.get(f"/api/admin/mail-log?{query}")
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    walked: list[int] = []
    cursor: str | None = ""
    while cursor is not None:
        page = (await env.get(f"/api/admin/mail-log?limit=2&cursor={cursor}")).json()
        walked += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
    assert walked == sorted(set(_fixture_rows()) - _V2_ROWS, reverse=True)
    assert await ids("template=signing_request&template=signing_reminder") == [1206, 1204]
    assert await ids("status=not_sent&status=suppressed") == [1203, 1202]
    assert await ids("reason=auth") == [1204]
    assert await ids("recipient_id=4e7a2d9c1b3f4a5e8d6c0b2a9f8e7d61") == [1207, 1203]
    assert await ids("recipient=%20Boris.Kovalev@EXAMPLE.org%20") == [1207, 1203]
    assert await ids(f"project_id={_PROJECT}&status=failed") == [1205, 1204]
    assert await ids("from=2026-11-11T09:00:02Z&to=2026-11-11T11:20:44Z") == [1205, 1204]
    assert await ids("q=REJECT-x") == [1205]
    assert await ids("q=%D1%81%D0%B1%D1%80%D0%BE%D1%81") == [1207]
    assert await ids("template=weekly_digest") == [1042]


async def test__page__names_come_in_one_lookup_per_page(env: _Env) -> None:
    env.seed_fixtures()

    await env.get("/api/admin/mail-log?limit=200")

    # Одна выборка людей и одна проектов на страницу, а не по строке.
    assert env.names.calls == 2


async def test__page__limit_is_bounded_and_extra_rows_mean_next_cursor(env: _Env) -> None:
    for n in range(3):
        await env.log.add(replace(_entry(_fixture_rows()[1207]), at=NOW - timedelta(minutes=n)))

    first = (await env.get("/api/admin/mail-log?limit=2")).json()

    assert [item["id"] for item in first["items"]] == [3, 2]
    assert first["next_cursor"] == encode_cursor(2)
    assert (await env.get("/api/admin/mail-log?limit=201")).status_code == 422
    assert (await env.get("/api/admin/mail-log?limit=0")).status_code == 422


# --- права и коды ошибок (6.3) ---


@pytest.mark.parametrize("path", ["/api/admin/mail-log", "/api/admin/mail-log/summary", "/api/admin/mail-log/1207"])
async def test__rights__only_the_instance_admin_by_session(env: _Env, path: str) -> None:
    env.seed_fixtures()

    anonymous = await env.get(path, headers={})
    user = await env.get(path, headers={"Authorization": "Bearer user"})
    pat = await env.get(path, headers={"Authorization": "Bearer admin-pat"})
    admin = await env.get(path)

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "auth_required"
    assert user.status_code == 404
    assert user.json()["code"] == "not_found"
    assert pat.status_code == 404
    assert admin.status_code == 200


@pytest.mark.parametrize(
    "query",
    [
        "status=bounced",
        "cursor=not-a-cursor",
        "from=2026-11-11T10:00:00Z&to=2026-11-11T09:00:00Z",
        "recipient_id=x&unknown=1",
        "to_email=a@example.org",
        "template=Bad-Kind",
        f"template={'a' * 65}",
        "reason=Bad",
        "project_id=not-a-uuid",
        f"q={'a' * 201}",
    ],
)
async def test__codes__bad_list_input_is_422(env: _Env, query: str) -> None:
    response = await env.get(f"/api/admin/mail-log?{query}")

    assert response.status_code == 422, query


async def test__codes__missing_entry_is_404(env: _Env) -> None:
    env.seed_fixtures()

    missing = await env.get("/api/admin/mail-log/999999")
    huge = await env.get(f"/api/admin/mail-log/{2**70}")
    zero = await env.get("/api/admin/mail-log/0")
    text = await env.get("/api/admin/mail-log/abc")

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert huge.status_code == 404
    assert zero.status_code == 404
    assert text.status_code == 422


# --- ни токена, ни ссылки, ни сообщения человека ---

_TOKEN = "Tk_known-secret-0123456789abcdef"  # noqa: S105 — известная строка теста, не секрет
_NOTE = "Личное сообщение: позвоните мне по номеру 8-900-000-00-00"


def _leaky_requests() -> list[MailRequest]:
    """Каждый вид письма со ссылкой, где токен это известная строка, и с сообщением человека."""
    values = {
        "actor": "Анна Петрова",
        "inviter": "Анна Петрова",
        "project": "Курсовая работа по ГОСТ",
        "role": "editor",
        "profile": "Заявка",
        "deadline": "15.11.2026, 23:59 (МСК)",
        "changed": "«Заявление»",
        "name": "MacBook",
        "count": "2",
        "signing": "ждём научного руководителя (Пётр Петров)",
    }
    requests: list[MailRequest] = []
    for template in MailTemplate:
        for lang in Lang:
            if fixed_path(template):
                kinds: list[tuple[MailLinkKind, str | None]] = [(MailLinkKind.page, None)]
            else:
                kinds = [
                    (MailLinkKind.token, f"{_SERVER}/reset/{_TOKEN}"),
                    (MailLinkKind.page, f"{_SERVER}{_SIGN}?token={_TOKEN}#{_TOKEN}"),
                ]
            for kind, link in kinds:
                requests.append(
                    MailRequest(
                        template=template,
                        lang=lang,
                        to=f"{template.value}@example.org",
                        server_url=_SERVER,
                        origin=MailOrigin.notification,
                        link_kind=kind,
                        link=link,
                        ttl=timedelta(hours=1),
                        values={key: values[key] for key in SAFE_VALUES[template]},
                        note=_NOTE,
                    )
                )
    return requests


async def test__no_response_contains_a_token_a_source_link_or_a_note(env: _Env) -> None:
    requests = _leaky_requests()
    for n, request in enumerate(requests):
        sent = request.render()
        # Письмо как ушло содержало токен; у видов без кнопки ссылки в письме нет, у постоянной страницы своя.
        linked = "action" in catalog(request.lang)["mails"][request.template.value]
        assert (_TOKEN in sent.text) is (linked and fixed_path(request.template) is None)
        await env.log.add(
            MailLogEntry(
                at=NOW - timedelta(minutes=n),
                duration_ms=5,
                template=request.template.value,
                lang=request.lang.value,
                to_email=request.to,
                subject=sent.subject,
                status=MailStatus.sent,
                cause=MailCause.anonymous,
                origin=request.origin.value,
                params=safe_params(request),
                template_digest=template_digest(request.template, request.lang),
                message_id=f"<{n}@studio.example.org>",
            )
        )
    bodies: list[str] = []
    cursor: str | None = ""
    while cursor is not None:
        page = await env.get(f"/api/admin/mail-log?limit=7&cursor={cursor}")
        bodies.append(page.text)
        cursor = page.json()["next_cursor"]
    for entry in env.log.entries:
        detail = await env.get(f"/api/admin/mail-log/{entry.id}")
        assert detail.status_code == 200
        assert detail.json()["preview"] is not None
        bodies.append(detail.text)
    bodies.append((await env.get("/api/admin/mail-log/summary")).text)

    assert len(bodies) > len(requests)
    for body in bodies:
        assert _TOKEN not in body
        assert "/reset/" not in body
        assert "?token=" not in body
        assert _NOTE not in body
        assert "8-900" not in body


# --- версия 2: повтор писем (раздел 14) ---


async def test__resend__sends_a_linked_row_and_answers_by_the_contract(env: _Env) -> None:
    env.seed_fixtures()

    response = await env.client.post("/api/admin/mail-log/1204/resend", headers=_ADMIN)  # type: ignore[union-attr]

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    AdminMailLogResendResult.model_validate(body)
    assert body["outcome"] == "sent"
    assert body["blocked"] is None
    new = await env.log.get(body["entry_id"])
    assert new is not None
    assert new.resent_from_id == 1204
    assert new.origin == MailOrigin.admin_resend.value
    assert env.audit.events == [("mail.resent", "1204")]
    detail = (await env.get("/api/admin/mail-log/1204")).json()
    assert detail["resend"] == {"allowed": False, "blocked": "already_resent"}
    assert [r["id"] for r in detail["resent"]] == [body["entry_id"]]


@pytest.mark.parametrize(("entry_id", "blocked"), [(1207, "status"), (1205, "token_link"), (1300, "retrying")])
async def test__resend__blocked_answers_200_with_the_reason(env: _Env, entry_id: int, blocked: str) -> None:
    env.seed_fixtures()

    response = await env.client.post(f"/api/admin/mail-log/{entry_id}/resend", headers=_ADMIN)  # type: ignore[union-attr]

    assert response.status_code == 200, response.text
    assert response.json() == {"outcome": "blocked", "blocked": blocked, "entry_id": None, "reason": None}
    assert env.sender.sent == []


async def test__resend__rights_and_missing_entry(env: _Env) -> None:
    env.seed_fixtures()
    client = env.client
    assert client is not None

    assert (
        await client.post("/api/admin/mail-log/1204/resend", headers={"Authorization": "Bearer user"})
    ).status_code == 404
    assert (await client.post("/api/admin/mail-log/1204/resend")).status_code == 401
    assert (await client.post("/api/admin/mail-log/99999/resend", headers=_ADMIN)).status_code == 404
    assert (
        await client.post("/api/admin/mail-log/resend", json={}, headers={"Authorization": "Bearer user"})
    ).status_code == 404


async def test__resend_batch__preview_then_start(env: _Env) -> None:
    env.seed_fixtures()
    client = env.client
    assert client is not None

    preview = await client.post("/api/admin/mail-log/resend", json={"dry_run": True}, headers=_ADMIN)

    assert preview.status_code == 200, preview.text
    body = preview.json()
    AdminMailLogResendBatch.model_validate(body)
    # 1204 уйдёт; 1301 уже повторено, 1205 и 1202 с токеном; 1300 ждёт автоповтора и в кандидаты не входит.
    assert body["planned"] == 1
    assert body["skipped"] == {"already_resent": 1, "token_link": 2}
    assert body["started"] is False

    started = await client.post(
        "/api/admin/mail-log/resend", json={"dry_run": False, "template": ["signing_reminder"]}, headers=_ADMIN
    )
    await drain_resend_batches()

    assert started.json()["started"] is True
    assert len(env.sender.sent) == 1
    assert env.audit.events[-1][0] == "mail.resent_batch"


@pytest.mark.parametrize(
    "payload",
    [{"since": "2026-11-12T00:00:00Z", "until": "2026-11-11T00:00:00Z"}, {"status": ["failed"]}, {"template": ["Bad"]}],
)
async def test__resend_batch__bad_body_is_422(env: _Env, payload: dict[str, Any]) -> None:
    client = env.client
    assert client is not None

    response = await client.post("/api/admin/mail-log/resend", json=payload, headers=_ADMIN)

    assert response.status_code == 422


async def test__page__retrying_filter(env: _Env) -> None:
    env.seed_fixtures()

    waiting = (await env.get("/api/admin/mail-log?retrying=true")).json()
    final = (await env.get("/api/admin/mail-log?status=failed&retrying=false")).json()

    assert [item["id"] for item in waiting["items"]] == [1300]
    assert 1300 not in [item["id"] for item in final["items"]]
    assert 1204 in [item["id"] for item in final["items"]]
