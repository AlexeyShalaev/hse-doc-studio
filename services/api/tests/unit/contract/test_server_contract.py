"""Контракт серверного режима: эталонные JSON из contracts/server против pydantic-моделей.

Те же файлы разбирает zod-тест фронтенда (entities/session/api/contract.test.ts). Форму меняют
так: сначала эталоны, затем обе стороны и оба набора тестов в одном коммите.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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
    "ChangePasswordRequest": s.ChangePasswordRequest,
    "ChangeEmailRequest": s.ChangeEmailRequest,
    "ChangeEmailResponse": s.ChangeEmailResponse,
    "AccountSession": s.AccountSession,
    "AccountSessionList": list[s.AccountSession],
    "ApiToken": s.ApiToken,
    "ApiTokenList": list[s.ApiToken],
    "CreateApiTokenRequest": s.CreateApiTokenRequest,
    "CreateApiTokenResponse": s.CreateApiTokenResponse,
    "ProjectSummary": s.ProjectSummary,
    "ProjectSummaryList": list[s.ProjectSummary],
    "CreateServerProjectRequest": s.CreateServerProjectRequest,
    "AdminUser": s.AdminUser,
    "AdminUserList": list[s.AdminUser],
    "AdminOrgList": list[s.AdminOrg],
    "AdminRunnerList": list[s.AdminRunner],
    "AdminSettings": s.AdminSettings,
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
