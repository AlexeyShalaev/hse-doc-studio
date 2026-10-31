"""Контракт серверного режима: эталонные JSON из contracts/server против pydantic-моделей.

Те же файлы разбирает zod-тест фронтенда (entities/session/api/contract.test.ts). Форму меняют
так: сначала эталоны, затем обе стороны и оба набора тестов в одном коммите.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas import admin as adm
from hse_doc_studio.api.schemas import admin_install as inst
from hse_doc_studio.api.schemas import admin_ops as ops
from hse_doc_studio.api.schemas import ai_providers as aip
from hse_doc_studio.api.schemas import git_remote as gr
from hse_doc_studio.api.schemas import personal_runners as pr
from hse_doc_studio.api.schemas import remote_runner as rr
from hse_doc_studio.api.schemas import runner_admin as ra
from hse_doc_studio.api.schemas import session as s
from pydantic import TypeAdapter, ValidationError

_REPO = Path(__file__).resolve().parents[5]
_CONTRACT = _REPO / "contracts" / "server"
_FIXTURES = _CONTRACT / "fixtures"
_LOCALES = _REPO / "services" / "web-app" / "src" / "shared" / "lib" / "i18n" / "locales"

# Каталог эталонов -> модель, которой он обязан соответствовать.
_SCHEMAS: dict[str, Any] = {
    "Bootstrap": s.BootstrapResponse,
    "SessionUser": s.SessionUser,
    "LoginRequest": s.LoginRequest,
    "LoginResponse": s.LoginResponse,
    "RegisterRequest": s.RegisterRequest,
    "RegisterResponse": s.RegisterResponse,
    "VerifyEmailRequest": s.VerifyEmailRequest,
    "InvitationInfo": s.InvitationInfo,
    "ResendVerificationRequest": s.ResendVerificationRequest,
    "ForgotRequest": s.ForgotRequest,
    "ForgotResponse": s.ForgotResponse,
    "ResetRequest": s.ResetRequest,
    "ServerSetupStatus": s.ServerSetupStatus,
    "ServerSetupAdminRequest": s.ServerSetupAdminRequest,
    "ServerSetupSettingsRequest": s.ServerSetupSettingsRequest,
    "ServerSetupEnvironment": s.ServerSetupEnvironment,
    "ServerSetupSettings": s.ServerSetupSettings,
    "AuthErrorBody": s.AuthErrorBody,
    "UpdateAccountRequest": s.UpdateAccountRequest,
    "AccountProfile": s.AccountProfile,
    "ChangePasswordRequest": s.ChangePasswordRequest,
    "ChangeEmailRequest": s.ChangeEmailRequest,
    "ChangeEmailResponse": s.ChangeEmailResponse,
    "AccountSession": s.AccountSession,
    "AccountSessionList": list[s.AccountSession],
    "AccountIdentity": s.AccountIdentity,
    "AccountIdentityList": list[s.AccountIdentity],
    "ApiToken": s.ApiToken,
    "ApiTokenList": list[s.ApiToken],
    "CreateApiTokenRequest": s.CreateApiTokenRequest,
    "CreateApiTokenResponse": s.CreateApiTokenResponse,
    "ProjectSummary": s.ProjectSummary,
    "ProjectSummaryList": list[s.ProjectSummary],
    "ProjectSummaryPage": s.ProjectSummaryPage,
    "CreateServerProjectRequest": s.CreateServerProjectRequest,
    "ProjectImportResult": s.ProjectImportResult,
    "AdminUser": s.AdminUser,
    "AdminUserList": s.AdminUserPage,
    "AdminUserFacets": s.AdminUserFacets,
    "AdminUserOrgList": s.AdminUserOrgPage,
    "AdminPickerList": adm.PickerList,
    "UpdateAdminUserRequest": s.UpdateAdminUserRequest,
    "AdminResetLinkRequest": s.AdminResetLinkRequest,
    "AdminResetLink": s.AdminResetLink,
    "AdminSessionsRevoked": s.AdminSessionsRevoked,
    "AdminRetentionSettings": s.AdminRetentionSettings,
    "AdminInvitation": s.AdminInvitation,
    "AdminInvitationList": s.AdminInvitationPage,
    "AdminAuditEvent": s.AdminAuditEvent,
    "AdminAuditList": s.AdminAuditPage,
    "CreateAdminInvitationRequest": s.CreateAdminInvitationRequest,
    "AdminInvitationCreated": s.AdminInvitationCreated,
    "AdminOrgList": s.AdminOrgPage,
    "AdminOrgMember": s.AdminOrgMember,
    "AdminOrgMemberList": s.AdminOrgMemberPage,
    "AdminOrgMemberFacets": s.AdminOrgMemberFacets,
    "AddAdminOrgMemberRequest": s.AddAdminOrgMemberRequest,
    "UpdateAdminOrgMemberRequest": s.UpdateAdminOrgMemberRequest,
    "CreateAdminOrgRequest": s.CreateAdminOrgRequest,
    "AdminGroup": s.AdminGroup,
    "AdminGroupList": s.AdminGroupPage,
    "AdminGroupMemberList": s.AdminGroupMemberPage,
    "CreateAdminGroupRequest": s.CreateAdminGroupRequest,
    "UpdateAdminGroupRequest": s.UpdateAdminGroupRequest,
    "MyOrg": s.MyOrg,
    "MyOrgList": list[s.MyOrg],
    "ProjectAccessEntry": s.ProjectAccessEntry,
    "ProjectAccessList": s.ProjectAccessPage,
    "ProjectAccessCandidate": s.ProjectAccessCandidate,
    "ProjectAccessCandidateList": s.ProjectAccessCandidateList,
    "ProjectTransferCandidateList": adm.PickerList,
    "AdminRunnerList": adm.Page[ra.RunnerInfo],
    "AdminRunnerSummary": ra.RunnerSummaryInfo,
    "AdminRunnerTokenList": adm.Page[ra.RegistrationTokenInfo],
    "CreateAdminRunnerTokenRequest": ra.CreateRegistrationTokenRequest,
    "AdminRunnerTokenCreated": ra.CreatedRegistrationTokenResponse,
    "AdminRunnerRotated": ra.RotatedRunnerTokenResponse,
    "UpdateAdminRunnerRequest": ra.UpdateRunnerRequest,
    "AdminJobPage": ops.AdminJobPage,
    "AdminQueueSummary": ops.AdminQueueSummary,
    "AdminQuotas": ops.AdminQuotas,
    "UpdateAdminQuotasRequest": ops.UpdateAdminQuotasRequest,
    "AdminServiceHealthList": list[ops.AdminServiceHealth],
    "AdminStorageUsage": ops.AdminStorageUsage,
    "AdminStorageOwnerList": adm.Page[ops.AdminStorageOwnerRow],
    "AdminSigningPolicy": ops.AdminSigningPolicy,
    "UpdateAdminSigningPolicyRequest": ops.UpdateAdminSigningPolicyRequest,
    "AdminAiProvider": ops.AdminAiProvider,
    "AdminAiProviderList": adm.Page[ops.AdminAiProvider],
    "CreateAdminAiProviderRequest": ops.CreateAdminAiProviderRequest,
    "UpdateAdminAiProviderRequest": ops.UpdateAdminAiProviderRequest,
    "AdminAiProviderCheck": ops.AdminAiProviderCheck,
    "AiProvider": aip.AIProviderResponse,
    "AiProviderList": list[aip.AIProviderResponse],
    "CreateAiProviderRequest": aip.CreateAIProviderRequest,
    "Org": s.Org,
    "CreateOrgRequest": s.CreateOrgRequest,
    "UpdateOrgRequest": s.UpdateOrgRequest,
    "OrgMember": s.OrgMember,
    "AddOrgMemberRequest": s.AddOrgMemberRequest,
    "ChangeOrgMemberRoleRequest": s.ChangeOrgMemberRoleRequest,
    "Group": s.Group,
    "CreateGroupRequest": s.CreateGroupRequest,
    "UpdateGroupRequest": s.UpdateGroupRequest,
    "GroupMember": s.GroupMember,
    "AddGroupMemberRequest": s.AddGroupMemberRequest,
    "ProjectMember": s.ProjectMember,
    "SetProjectMemberRequest": s.SetProjectMemberRequest,
    "AdminSettings": s.AdminSettings,
    "AdminRegistrationSettings": s.AdminRegistrationSettings,
    "UpdateAdminRegistrationRequest": s.UpdateAdminRegistrationRequest,
    "AdminAuthSettings": s.AdminAuthSettings,
    "UpdateAdminAuthRequest": s.UpdateAdminAuthRequest,
    "AdminSmtpSettings": s.AdminSmtpSettings,
    "AdminInstanceSettings": inst.AdminInstanceSettings,
    "UpdateAdminInstanceRequest": inst.UpdateAdminInstanceRequest,
    "AdminBuildSettings": inst.AdminBuildSettings,
    "UpdateAdminBuildRequest": inst.UpdateAdminBuildRequest,
    "UpdateAdminSmtpRequest": s.UpdateAdminSmtpRequest,
    "AdminSmtpTestRequest": s.AdminSmtpTestRequest,
    "AdminSmtpTestResult": s.AdminSmtpTestResult,
    "AdminOidcProvider": s.AdminOidcProvider,
    "AdminOidcProviderList": s.AdminOidcProviderPage,
    "CreateAdminOidcProviderRequest": s.CreateAdminOidcProviderRequest,
    "UpdateAdminOidcProviderRequest": s.UpdateAdminOidcProviderRequest,
    "CompileWait": s.CompileWait,
    "OfficeEditorBusy": s.OfficeEditorBusy,
    "MyRunner": pr.MyRunner,
    "MyRunnerList": list[pr.MyRunner],
    "UpdateMyRunnerRequest": pr.UpdateMyRunnerRequest,
    "MyRunnerRotated": pr.MyRunnerRotated,
    "MyRunnerTokenList": list[pr.MyRunnerToken],
    "CreateMyRunnerTokenRequest": pr.CreateMyRunnerTokenRequest,
    "MyRunnerTokenCreated": pr.MyRunnerTokenCreated,
    "RunnerPairingInfo": pr.RunnerPairingInfo,
    "RunnerPairingDecisionRequest": pr.RunnerPairingDecisionRequest,
    "ProjectBuildRunners": pr.ProjectBuildRunners,
    "UpdateProjectBuildRunnersRequest": pr.UpdateProjectBuildRunnersRequest,
    "CompilePlacement": pr.CompilePlacement,
    "RemoteRunnerStatus": rr.RemoteRunnerStatus,
    "UpdateRemoteRunnerRequest": rr.UpdateRemoteRunnerRequest,
    "RemoteRunnerPairRequest": rr.RemoteRunnerPairRequest,
    "RemoteRunnerTokenRequest": rr.RemoteRunnerTokenRequest,
    # gitremote: git по HTTPS, вход устройства, адрес клонирования, вход локальной Студии на сервер
    "GitServerInfo": gr.GitServerInfo,
    "GitWhoami": gr.GitWhoami,
    "GitProjectPage": gr.GitProjectPage,
    "GitServerProjectPage": gr.GitProjectPage,
    "DeviceCodeRequest": gr.DeviceCodeRequest,
    "DeviceCodeResponse": gr.DeviceCodeResponse,
    "DeviceTokenRequest": gr.DeviceTokenRequest,
    "DeviceTokenResponse": gr.DeviceTokenResponse,
    "DeviceTokenError": gr.DeviceTokenError,
    "DeviceAuthorizationInfo": gr.DeviceAuthorizationInfo,
    "DeviceDecisionRequest": gr.DeviceDecisionRequest,
    "ProjectGitRemote": gr.ProjectGitRemote,
    "GitServerLoginRequest": gr.GitServerLoginRequest,
    "GitServerLogin": gr.GitServerLogin,
    "GitServerList": gr.GitServerList,
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixtures() -> list[tuple[str, str, Path]]:
    return [(d.name, f.stem, f) for d in sorted(_FIXTURES.iterdir()) if d.is_dir() for f in sorted(d.glob("*.json"))]


_CASES = _fixtures()
_CODES: list[str] = _read(_CONTRACT / "error_codes.json")


def test_every_fixture_directory_has_a_schema() -> None:
    dirs = sorted(d.name for d in _FIXTURES.iterdir() if d.is_dir())
    assert dirs == sorted(_SCHEMAS)


@pytest.mark.parametrize(("schema", "name", "path"), _CASES, ids=[f"{a}/{b}" for a, b, _ in _CASES])
def test_fixture_matches_model(schema: str, name: str, path: Path) -> None:
    adapter = TypeAdapter(_SCHEMAS[schema])
    body = _read(path)
    parsed = adapter.validate_python(body)
    # Обратная сериализация не теряет полей: эталон содержит все поля явно, в том числе null.
    dumped = adapter.dump_python(parsed, mode="json")
    assert _normalize(dumped) == _normalize(body)


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, str) and value.endswith(("Z", "+00:00")) and "T" in value:
        return value.replace("+00:00", "Z")
    return value


@pytest.mark.parametrize(("schema", "name", "path"), _CASES, ids=[f"{a}/{b}" for a, b, _ in _CASES])
def test_unknown_field_is_rejected(schema: str, name: str, path: Path) -> None:
    body = _read(path)
    adapter = TypeAdapter(_SCHEMAS[schema])
    if isinstance(body, list):
        if not body:
            pytest.skip("пустой список")
        body[0]["surprise"] = 1
    else:
        body["surprise"] = 1
    with pytest.raises(ValidationError):
        adapter.validate_python(body)


def test_unknown_mode_is_rejected() -> None:
    body = _read(_FIXTURES / "Bootstrap" / "local.json")
    body["mode"] = "cloud"
    with pytest.raises(ValidationError):
        s.BootstrapResponse.model_validate(body)


def test_error_codes_are_unique_and_snake_case() -> None:
    assert len(set(_CODES)) == len(_CODES)
    assert all(c == c.lower() and " " not in c for c in _CODES)


def test_fixture_error_codes_are_in_catalog() -> None:
    used = {_read(f)["code"] for d, _, f in _CASES if d == "AuthErrorBody"}
    assert used <= set(_CODES)


@pytest.mark.parametrize("lng", ["ru", "en"])
def test_every_code_has_a_message(lng: str) -> None:
    messages = _read(_LOCALES / lng / "errors.json")["code"]
    assert [c for c in _CODES if not str(messages.get(c, "")).strip()] == []


def test_bootstrap_variants_cover_states() -> None:
    boots = [_read(f) for d, _, f in _CASES if d == "Bootstrap"]
    assert {b["mode"] for b in boots} == {"local", "server"}
    assert {b["setup_state"] for b in boots} == {"needs_admin", "ready"}
    assert any(b["user"] is None for b in boots)
    assert any(b["user"] and b["user"]["is_instance_admin"] for b in boots)
    assert any(not b["auth"]["password_enabled"] for b in boots)


def test_setup_settings_domains_mode_needs_a_domain() -> None:
    body = _read(_FIXTURES / "ServerSetupSettingsRequest" / "domains.json")
    body["registration_domains"] = [" @ "]

    with pytest.raises(ValidationError):
        s.ServerSetupSettingsRequest.model_validate(body)


def test_setup_admin_request_needs_a_valid_email() -> None:
    body = _read(_FIXTURES / "ServerSetupAdminRequest" / "with_token.json")
    body["email"] = "not-an-email"

    with pytest.raises(ValidationError):
        s.ServerSetupAdminRequest.model_validate(body)


def test_setup_environment_covers_ok_fail_and_not_configured() -> None:
    envs = [_read(f) for d, _, f in _CASES if d == "ServerSetupEnvironment"]
    statuses = {c["status"] for e in envs for c in e["checks"]}
    assert statuses == {"ok", "fail", "not_configured"}


def test_add_admin_org_member_needs_exactly_one_way() -> None:
    body = _read(_FIXTURES / "AddAdminOrgMemberRequest" / "by_user.json")
    body["email"] = "anna@example.org"

    with pytest.raises(ValidationError):
        s.AddAdminOrgMemberRequest.model_validate(body)


def test_bootstrap_capabilities_offer_personal_runners_only_to_signed_in_server_users() -> None:
    boots = {name: _read(f)["capabilities"] for d, name, f in _CASES if d == "Bootstrap"}
    assert {name for name, caps in boots.items() if caps["personal_runners"]} == {"server_user", "server_admin"}
    assert {name for name, caps in boots.items() if caps["remote_runner"]} == {"local"}


def test_owner_runner_chips_carry_only_name_and_state() -> None:
    # Соавтор не видит у раннера владельца ничего, кроме имени и состояния.
    assert set(pr.OwnerRunnerChip.model_fields) == {"name", "state"}
    assert set(pr.CompilePlacement.model_fields) == {"state", "runner_name", "runner_owner", "fallback", "wait_s"}
