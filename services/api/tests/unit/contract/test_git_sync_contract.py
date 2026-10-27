"""Контракт Git-синхронизации: эталонные JSON из contracts/git-sync против pydantic-моделей.

Те же файлы разбирает zod-тест фронтенда (entities/git-sync/api/contract.test.ts), поэтому
расхождение сторон ловится на любой из них. Форму меняют так: сначала эталоны, затем обе
стороны и оба набора тестов в одном коммите.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas import git_sync as s
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.providers import (
    DetectedBy,
    GitProvider,
    Sufficiency,
    assess_scopes,
    provider_for_host,
)
from pydantic import TypeAdapter

_REPO = Path(__file__).resolve().parents[5]
_CONTRACT = _REPO / "contracts" / "git-sync"
_FIXTURES = _CONTRACT / "fixtures"
_LOCALES = _REPO / "services" / "web-app" / "src" / "shared" / "lib" / "i18n" / "locales"

# Каталог эталонов -> модель, которой он обязан соответствовать.
_SCHEMAS: dict[str, Any] = {
    "GitErrorBody": s.GitErrorBody,
    "ProfileValidationError": s.ProfileValidationError,
    "Profile": s.ProfileResponse,
    "ProfileRequest": s.ProfileRequest,
    "GitCredential": s.GitCredentialResponse,
    "GitCredentialList": list[s.GitCredentialResponse],
    "GitCredentialCheck": s.GitCredentialCheckResponse,
    "CreateCredentialRequest": s.CreateCredentialRequest,
    "UpdateCredentialRequest": s.UpdateCredentialRequest,
    "GitHostList": list[s.GitHostResponse],
    "GitHostSettings": s.GitHostSettingsResponse,
    "GitHostSettingsList": list[s.GitHostSettingsResponse],
    "UpdateGitHostSettingsRequest": s.UpdateGitHostSettingsRequest,
    "TrustHostRequest": s.TrustHostRequest,
    "SecretsStatus": s.SecretsStatusResponse,
    "SharedFolder": s.SharedFolderResponse,
    "CloneDefaults": s.CloneDefaultsResponse,
    "Probe": s.ProbeResponse,
    "ProbeRequest": s.ProbeRequest,
    "OperationStarted": s.OperationStartedResponse,
    "SyncResult": s.SyncResult,
    "CloneResult": s.CloneResult,
    "Operation": s.OperationResponse,
    "CloneRequest": s.CloneRequest,
    "GitStatus": s.GitStatusResponse,
    "ConnectRemoteRequest": s.ConnectRemoteRequest,
    "UpdateGitSettingsRequest": s.UpdateGitSettingsRequest,
    "GitContents": s.GitContentsResponse,
    "ConflictSession": s.ConflictSessionResponse,
    "ConflictFileDetail": s.ConflictFileDetail,
    "ConflictDiff": s.ConflictDiffResponse,
    "ResolveConflictsRequest": s.ResolveConflictsRequest,
    "SaveConflictDraftRequest": s.SaveConflictDraftRequest,
    "CiRequest": s.CiRequest,
    "CiWriteRequest": s.CiWriteRequest,
    "CiPreview": s.CiPreviewResponse,
    "CiWrite": s.CiWriteResponse,
    "HistoryCommit": s.HistoryCommitResponse,
    "HistoryFacets": s.HistoryFacetsResponse,
}

_UI_STATES = {
    "no_remote",
    "unfetched",
    "up_to_date",
    "ahead",
    "behind",
    "diverged",
    "syncing",
    "conflicts",
    "auth_failed",
    "offline",
    "error",
    "blocked",
}
_RELATIONS = {"none", "unfetched", "remote_empty", "in_sync", "ahead", "behind", "diverged"}
_HEALTH = {"ok", "unauthenticated", "offline", "error", "host_key_changed", "remote_missing", "branch_missing"}
_BLOCKED = {"off_branch", "read_only", "remote_schema_newer", "store_untrusted", "profile_required"}
_PROBE_RELATIONS = {
    "empty",
    "studio_project",
    "same_project",
    "same_project_unrelated_history",
    "other_project",
    "not_studio_project",
    "unknown",
}
_OPERATION_KINDS = {"sync", "resolve", "connect", "clone", "bundle_import"}
_OPERATION_STATUSES = {"running", "succeeded", "failed", "cancelled"}
_OPERATION_PHASES = {"queued", "snapshot", "fetch", "merge", "push", "download", "verify", "register"}
_OUTCOMES = {"up_to_date", "pushed", "fast_forwarded", "merged", "conflicts"}
_DETAIL_KINDS = {"text", "json", "binary", "delete"}
_RESOLUTION_KINDS = {"file", "hunks", "fields", "text"}
_CREDENTIAL_KINDS = {"pat", "ssh_key"}
_CREDENTIAL_STATUSES = {"unverified", "ok", "auth_failed", "unreadable"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_files() -> list[Path]:
    return sorted(_FIXTURES.glob("*/*.json"))


def _fixtures_of(schema: str) -> list[Any]:
    return [_load(path) for path in sorted((_FIXTURES / schema).glob("*.json"))]


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _values(schema: str, key: str) -> set[Any]:
    return {
        node[key] for body in _fixtures_of(schema) for node in _walk(body) if isinstance(node, dict) and key in node
    }


def _error_codes() -> list[str]:
    return _load(_CONTRACT / "error_codes.json")


# --- коды ошибок --------------------------------------------------------------


def test_error_codes_json_matches_enum() -> None:
    codes = _error_codes()
    assert len(codes) == len(set(codes))
    assert codes == [code.value for code in GitErrorCode]


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_every_error_code_has_a_message_in_each_locale(locale: str) -> None:
    messages = _load(_LOCALES / locale / "errors.json")["code"]
    missing = [code for code in _error_codes() if not str(messages.get(code, "")).strip()]
    assert not missing


def test_fixture_codes_belong_to_the_closed_list() -> None:
    known = set(_error_codes())
    for path in _fixture_files():
        for node in _walk(_load(path)):
            if isinstance(node, dict) and "code" in node and "detail" in node:
                assert node["code"] in known, f"{path.name}: {node['code']}"


# --- эталоны ------------------------------------------------------------------


def test_every_fixture_directory_has_a_schema() -> None:
    directories = {path.name for path in _FIXTURES.iterdir() if path.is_dir()}
    assert directories == set(_SCHEMAS)
    assert all(_fixtures_of(name) for name in directories)


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda path: f"{path.parent.name}/{path.stem}")
def test_fixture_validates_and_round_trips(path: Path) -> None:
    adapter = TypeAdapter(_SCHEMAS[path.parent.name])
    body = _load(path)
    model = adapter.validate_python(body)
    assert adapter.dump_python(model, mode="json", exclude_unset=True) == body


def test_status_fixtures_cover_every_state() -> None:
    assert _values("GitStatus", "ui_state") == _UI_STATES
    assert _values("GitStatus", "relation") <= _RELATIONS
    assert _values("GitStatus", "health") <= _HEALTH
    assert _values("GitStatus", "reason") <= _BLOCKED
    assert {"unauthenticated", "offline", "remote_missing", "host_key_changed"} <= _values("GitStatus", "health")


def test_probe_fixtures_cover_every_relation() -> None:
    assert _values("Probe", "relation") == _PROBE_RELATIONS
    assert {"auth_failed", "offline", "host_key_unknown"} <= {
        body["error"]["code"] for body in _fixtures_of("Probe") if body["error"]
    }


def test_operation_fixtures_cover_kinds_statuses_and_phases() -> None:
    operations = _fixtures_of("Operation")
    assert {body["kind"] for body in operations} == _OPERATION_KINDS
    assert {body["status"] for body in operations} == _OPERATION_STATUSES
    assert {body["phase"] for body in operations} == _OPERATION_PHASES
    assert {body["result"]["outcome"] for body in operations if body["result"] and "outcome" in body["result"]}


def test_sync_result_fixtures_cover_every_outcome() -> None:
    assert {body["outcome"] for body in _fixtures_of("SyncResult")} == _OUTCOMES


def test_conflict_fixtures_cover_every_file_kind_and_resolution() -> None:
    assert {body["kind"] for body in _fixtures_of("ConflictFileDetail")} == _DETAIL_KINDS
    saved = {body["kind"] for body in _fixtures_of("SaveConflictDraftRequest")[0]["resolutions"].values()}
    assert saved == _RESOLUTION_KINDS


def test_credential_fixtures_stay_within_known_values() -> None:
    assert _values("GitCredential", "kind") == _CREDENTIAL_KINDS
    assert _values("GitCredential", "status") <= _CREDENTIAL_STATUSES


def test_history_fixtures_carry_the_sync_kind_and_markers() -> None:
    commits = _fixtures_of("HistoryCommit")
    assert {body["sync"] for body in commits} == {"unpushed", "incoming", None}
    assert any(body["is_merge"] for body in commits)
    assert "sync" in _fixtures_of("HistoryFacets")[0]["kinds"]


def test_secrets_never_appear_in_response_fixtures() -> None:
    forbidden = {"token", "password", "secret", "private_key"}
    for schema in ("GitCredential", "GitCredentialList", "Probe", "GitStatus", "SecretsStatus"):
        for body in _fixtures_of(schema):
            keys = {key for node in _walk(body) if isinstance(node, dict) for key in node}
            assert not keys & forbidden, schema


def _provider_infos() -> list[tuple[str, dict[str, Any], str | None]]:
    """(схема, provider_info, хост) из всех эталонов, где он есть."""
    found: list[tuple[str, dict[str, Any], str | None]] = []
    for path in _fixture_files():
        for node in _walk(_load(path)):
            if isinstance(node, dict) and "provider_info" in node and node["provider_info"] is not None:
                found.append(
                    (path.parent.name, node["provider_info"], node.get("host") or (node.get("url") or {}).get("host"))
                )
    return found


def test_provider_info_fixtures_use_the_provider_catalog() -> None:
    infos = _provider_infos()
    assert {info["id"] for _, info, _ in infos} <= {provider.value for provider in GitProvider}
    assert {info["detected_by"] for _, info, _ in infos} == {mode.value for mode in DetectedBy}
    for schema, info, host in infos:
        if info["detected_by"] == "host":
            assert provider_for_host(host).value == info["id"], f"{schema}: {host}"
        if info["detected_by"] == "unknown":
            assert info["id"] == "other"
            assert info["version"] is None


def test_probe_provider_matches_provider_info() -> None:
    for body in _fixtures_of("Probe"):
        assert body["url"]["provider"] == body["provider_info"]["id"]
    for body in _fixtures_of("GitStatus"):
        if body["remote"]:
            assert body["remote"]["provider"] == body["remote"]["provider_info"]["id"]


def test_token_info_fixtures_agree_with_the_scope_rules() -> None:
    infos = [(body["url"]["provider"], body["token_info"]) for body in _fixtures_of("Probe") if body["token_info"]]
    assert {info["sufficiency"] for _, info in infos} == {mode.value for mode in Sufficiency}
    for provider, info in infos:
        assert bool(info["missing"]) == (info["sufficiency"] == "too_narrow")
        if info["sufficiency"] != "unknown":
            verdict = assess_scopes(provider, info["scopes"])
            assert (verdict.sufficiency.value, list(verdict.missing)) == (info["sufficiency"], info["missing"])


def test_credential_fixtures_carry_expiry_for_tokens_only() -> None:
    credentials = _fixtures_of("GitCredential")
    assert any(body["expires_at"] for body in credentials)
    assert all(body["expires_at"] is None for body in credentials if body["kind"] == "ssh_key")


def test_tls_and_token_error_fixtures_carry_their_details() -> None:
    errors = {body["code"]: body for body in _fixtures_of("GitErrorBody")}
    assert errors["tls_untrusted_ca"]["certificate"]["fingerprint_sha256"].startswith("SHA256:")
    assert {"expected", "actual"} <= set(errors["tls_pin_mismatch"])
    probe_codes = {body["error"]["code"] for body in _fixtures_of("Probe") if body["error"]}
    assert {"token_expired", "tls_untrusted_ca", "tls_pin_mismatch"} <= probe_codes
    pin = next(
        body["error"] for body in _fixtures_of("Probe") if body["error"] and body["error"]["code"] == "tls_pin_mismatch"
    )
    assert {"expected", "actual"} <= set(pin)


def test_credential_check_fixtures_cover_checkable_and_unchecked_providers() -> None:
    checks = _fixtures_of("GitCredentialCheck")
    assert any(body["token_info"] for body in checks)
    assert any(body["token_info"] is None for body in checks)
    for body in checks:
        assert body["credential"]["kind"] == "pat"
        if body["token_info"] and body["token_info"]["sufficiency"] != "unknown":
            verdict = assess_scopes(body["provider_info"]["id"], body["token_info"]["scopes"])
            assert verdict.sufficiency.value == body["token_info"]["sufficiency"]


# --- векторы разбора адреса ---------------------------------------------------


def _url_cases() -> list[dict[str, Any]]:
    return _load(_CONTRACT / "url_cases.json")["cases"]


def test_url_cases_are_well_formed() -> None:
    cases = _url_cases()
    names = [case["name"] for case in cases]
    assert len(names) == len(set(names))
    known = set(_error_codes())
    assert {"url_invalid", "url_scheme_forbidden"} <= {case["error"] for case in cases if not case["ok"]}
    for case in cases:
        assert set(case.get("policy", {})) <= {"allow_http", "allow_local"}
        if case["ok"]:
            url = s.ProbeUrl.model_validate(case["url"])
            authority = url.display_url.split("://", 1)[1].split("/", 1)[0]
            assert url.kind == "ssh" or "@" not in authority
        else:
            assert case["error"] in known
