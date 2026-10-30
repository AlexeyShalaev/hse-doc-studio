from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.office_tokens import OfficeTokenPurpose, OfficeTokenSigner
from hse_doc_studio.infra.office.jwt import sign
from hse_doc_studio.infra.office.pooled_editor import ConfiguredReachability, PooledOfficeEditorService
from hse_doc_studio.infra.services.pool import ServicePool
from hse_doc_studio.use_cases.office_editor.access import LocalOfficeAccess, ServerOfficeAccess
from hse_doc_studio.use_cases.office_editor.get_editor_config import GetOfficeEditorConfigInput, GetOfficeEditorConfigUC
from hse_doc_studio.use_cases.office_editor.handle_callback import OfficeEditorCallbackInput, OfficeEditorCallbackUC

from tests.factories import make_document, make_project, make_template_version
from tests.fakes.settings import InMemorySettingsRepository
from tests.unit.use_cases.office_editor.test_get_editor_config import _pres_definition

_SECRET = "ds-secret"  # noqa: S105
_PATH = "pres/pptx/presentation.pptx"


class FakeAcl:
    def __init__(self) -> None:
        self.roles: dict[tuple[UUID, str], Role] = {}

    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        role = self.roles.get((project_id, actor.id or ""))
        if role is None:
            return None
        return ProjectAcl(str(project_id), grants={actor.id or "": Grant(role)})

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        raise NotImplementedError


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(autouse=True)
def _reset_actor():
    set_current_actor(None)
    yield
    set_current_actor(None)


class FakeUsers:
    """Любой id считается действующим аккаунтом, кроме перечисленных в `disabled` и `missing`."""

    def __init__(self) -> None:
        self.disabled: set[str] = set()
        self.missing: set[str] = set()

    async def get(self, user_id: str) -> User | None:
        if user_id in self.missing:
            return None
        status = UserStatus.disabled if user_id in self.disabled else UserStatus.active
        return User(user_id, f"{user_id}@example.org", f"{user_id}@example.org", user_id, status, datetime.now(UTC))


def _access(acl: FakeAcl, clock: Clock | None = None, users: FakeUsers | None = None) -> ServerOfficeAccess:
    return ServerOfficeAccess(
        OfficeTokenSigner([b"k" * 32]),
        acl,
        users or FakeUsers(),  # type: ignore[arg-type]
        ttl_s=600,
        clock=clock or Clock(),
    )


@pytest.mark.unit
async def test__local_access__issues_nothing() -> None:
    access = LocalOfficeAccess()

    assert not access.enforced
    assert await access.issue(uuid4(), "pres", _PATH) is None


@pytest.mark.unit
async def test__issue__editor__tokens_carry_role_and_nonce() -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    access = _access(acl)

    tokens = await access.issue(project_id, "pres", _PATH)

    assert tokens is not None
    assert tokens.role == "editor"
    claims = OfficeTokenSigner([b"k" * 32]).verify(
        tokens.callback, Clock().now, purpose=OfficeTokenPurpose.callback, project_id=str(project_id), doc_id="pres"
    )
    assert (claims.actor_id, claims.role, claims.nonce, claims.path) == ("u-1", "editor", tokens.nonce, _PATH)
    assert tokens.document != tokens.callback


@pytest.mark.unit
@pytest.mark.parametrize("role", [None, Role.reader, Role.reviewer])
async def test__issue__without_write_rights__denied(role: Role | None) -> None:
    acl, project_id = FakeAcl(), uuid4()
    if role is not None:
        acl.roles[(project_id, "u-1")] = role
    set_current_actor(Actor.user("u-1"))

    with pytest.raises(PermissionError):
        await _access(acl).issue(project_id, "pres", _PATH)


@pytest.mark.unit
async def test__authorize__role_revoked_after_issue__denied() -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    access = _access(acl)
    tokens = await access.issue(project_id, "pres", _PATH)
    assert tokens is not None
    assert (await access.authorize(tokens.callback, OfficeTokenPurpose.callback, project_id, "pres")).id == "u-1"

    acl.roles[(project_id, "u-1")] = Role.reader

    with pytest.raises(PermissionError):
        await access.authorize(tokens.callback, OfficeTokenPurpose.callback, project_id, "pres")


@pytest.mark.unit
async def test__authorize__expired_wrong_purpose_or_path__denied() -> None:
    acl, project_id, clock = FakeAcl(), uuid4(), Clock()
    acl.roles[(project_id, "u-1")] = Role.owner
    set_current_actor(Actor.user("u-1"))
    access = _access(acl, clock)
    tokens = await access.issue(project_id, "pres", _PATH)
    assert tokens is not None

    with pytest.raises(PermissionError):
        await access.authorize(tokens.document, OfficeTokenPurpose.callback, project_id, "pres")
    with pytest.raises(PermissionError):
        await access.authorize(tokens.callback, OfficeTokenPurpose.callback, project_id, "pres", "other/file.pptx")
    clock.now += timedelta(seconds=601)
    with pytest.raises(PermissionError):
        await access.authorize(tokens.callback, OfficeTokenPurpose.callback, project_id, "pres")


@pytest.mark.unit
async def test__issue__guest__denied() -> None:
    set_current_actor(Actor.guest("link-1"))

    with pytest.raises(PermissionError):
        await _access(FakeAcl()).issue(uuid4(), "pres", _PATH)


# ── сценарии поверх настоящих сервисов ──────────────────────────────────────


def _pool_manager(max_sessions: int = 1) -> PooledOfficeEditorService:
    async def probe(url: str) -> bool:  # noqa: ARG001
        return True

    return PooledOfficeEditorService(
        ServicePool("onlyoffice", ["http://ds-1", "http://ds-2"]), _SECRET, probe, max_sessions=max_sessions
    )


def _config_uc(project, manager, access) -> GetOfficeEditorConfigUC:  # noqa: ANN001
    template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=(_pres_definition(),))
    reachability = ConfiguredReachability("http://api:8000")
    uc = GetOfficeEditorConfigUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
        manager=manager,
        reachability=reachability,
        settings_repo=InMemorySettingsRepository(),
        access=access,
        busy_retry_after_s=17,
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc


def _pptx_project(tmp_path: Path):  # noqa: ANN202
    (tmp_path / "pres" / "pptx").mkdir(parents=True)
    (tmp_path / "pres" / "pptx" / "presentation.pptx").write_bytes(b"PK-pptx")
    return make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])


@pytest.mark.unit
async def test__editor_config__server__tokens_in_urls_and_sticky_replica(tmp_path: Path) -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    manager = _pool_manager(max_sessions=3)
    uc = _config_uc(_pptx_project(tmp_path), manager, _access(acl))

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id="pres"))

    assert out.state == "ready"
    config = out.config or {}
    key = config["document"]["key"]
    assert out.editor_base_url == manager.base_url_for(key)
    assert "?office_token=o1." in config["document"]["url"]
    assert "&office_token=o1." in config["editorConfig"]["callbackUrl"]
    assert config["editorConfig"]["callbackUrl"].startswith("http://api:8000/api/v1/office-editor/callback?")
    assert config["editorConfig"]["user"]["id"] == "u-1"
    assert manager.active_sessions == 1


@pytest.mark.unit
async def test__editor_config__over_limit__editor_busy_with_retry_hint(tmp_path: Path) -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    manager = _pool_manager(max_sessions=1)
    manager.try_open_session("someone-else")
    uc = _config_uc(_pptx_project(tmp_path), manager, _access(acl))

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id="pres"))

    assert out.state == "editor_busy"
    assert out.retry_after_s == 17
    assert out.limit == 1
    assert out.config is None


@pytest.mark.unit
async def test__editor_config__reader__denied_before_session_is_taken(tmp_path: Path) -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.reader
    set_current_actor(Actor.user("u-1"))
    manager = _pool_manager()
    uc = _config_uc(_pptx_project(tmp_path), manager, _access(acl))

    with pytest.raises(PermissionError):
        await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id="pres"))
    assert manager.active_sessions == 0


def _callback_uc(project, manager, access, client=None):  # noqa: ANN001, ANN202
    template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=(_pres_definition(),))
    put_file_uc = AsyncMock()
    seen: list[Actor | None] = []

    async def record(_inp):  # noqa: ANN001, ANN202
        from hse_doc_studio.core.access.context import current_actor  # noqa: PLC0415

        seen.append(current_actor())

    put_file_uc.execute.side_effect = record
    uc = OfficeEditorCallbackUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
        manager=manager,
        put_file_uc=put_file_uc,
        dispatcher=MagicMock(),
        settings_repo=InMemorySettingsRepository(),
        client=client or MagicMock(),
        access=access,
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc, put_file_uc, seen


def _save_inp(project_id: UUID, token: str | None) -> OfficeEditorCallbackInput:
    body = {
        "status": 2,
        "key": "key-1",
        "url": "http://ds-internal:80/cache/files/data/output.pptx?md5=x",
        "token": sign({"status": 2, "key": "key-1"}, _SECRET),
    }
    return OfficeEditorCallbackInput(project_id=project_id, doc_id="pres", sig="", body=body, office_token=token)


@pytest.mark.unit
async def test__callback__server_token_and_rights__saves_as_session_owner(tmp_path: Path) -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    access = _access(acl)
    tokens = await access.issue(project_id, "pres", _PATH)
    assert tokens is not None
    set_current_actor(None)  # колбэк приходит от контейнера без входа
    manager = _pool_manager()
    manager.try_open_session("key-1")
    client = MagicMock()
    client.get.return_value = SimpleNamespace(status_code=200, content=b"EDITED")
    uc, put_file_uc, seen = _callback_uc(_pptx_project(tmp_path), manager, access, client)

    assert await uc.execute(_save_inp(project_id, tokens.callback)) == {"error": 0}

    put_file_uc.execute.assert_awaited_once()
    assert [a.id for a in seen if a] == ["u-1"]
    assert client.get.call_args.args[0].startswith(manager.base_url_for("key-1") or "?")
    assert manager.active_sessions == 0
    from hse_doc_studio.core.access.context import current_actor  # noqa: PLC0415

    assert current_actor() is None


@pytest.mark.unit
async def test__callback__access_revoked__rejected_and_nothing_written(tmp_path: Path) -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    access = _access(acl)
    tokens = await access.issue(project_id, "pres", _PATH)
    assert tokens is not None
    del acl.roles[(project_id, "u-1")]
    uc, put_file_uc, _ = _callback_uc(_pptx_project(tmp_path), _pool_manager(), access)

    with pytest.raises(PermissionError):
        await uc.execute(_save_inp(project_id, tokens.callback))
    put_file_uc.execute.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("token", [None, "", "o1.garbage.sig"])
async def test__callback__server_without_valid_token__rejected(tmp_path: Path, token: str | None) -> None:
    access = _access(FakeAcl())
    uc, put_file_uc, _ = _callback_uc(_pptx_project(tmp_path), _pool_manager(), access)

    with pytest.raises(PermissionError):
        await uc.execute(_save_inp(uuid4(), token))
    put_file_uc.execute.assert_not_awaited()


@pytest.mark.unit
async def test__callback__document_token_is_not_a_callback_token(tmp_path: Path) -> None:
    acl, project_id = FakeAcl(), uuid4()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    access = _access(acl)
    tokens = await access.issue(project_id, "pres", _PATH)
    assert tokens is not None
    uc, put_file_uc, _ = _callback_uc(_pptx_project(tmp_path), _pool_manager(), access)

    with pytest.raises(PermissionError):
        await uc.execute(_save_inp(project_id, tokens.document))
    put_file_uc.execute.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("state", ["disabled", "missing"])
@pytest.mark.parametrize("purpose", [OfficeTokenPurpose.document, OfficeTokenPurpose.callback])
async def test__authorize__account_disabled_or_deleted__tokens_stop_working(
    state: str, purpose: OfficeTokenPurpose
) -> None:
    acl, project_id, users = FakeAcl(), uuid4(), FakeUsers()
    acl.roles[(project_id, "u-1")] = Role.editor
    set_current_actor(Actor.user("u-1"))
    access = _access(acl, users=users)
    tokens = await access.issue(project_id, "pres", _PATH)
    assert tokens is not None
    token = tokens.document if purpose is OfficeTokenPurpose.document else tokens.callback
    assert (await access.authorize(token, purpose, project_id, "pres")).id == "u-1"

    getattr(users, state).add("u-1")

    with pytest.raises(PermissionError):
        await access.authorize(token, purpose, project_id, "pres")
