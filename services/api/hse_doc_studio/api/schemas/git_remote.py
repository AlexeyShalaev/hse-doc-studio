"""Контракт git по HTTPS: служебные вызовы `/git/-/*`, вход устройства (device flow), адрес клонирования проекта
и вызовы локальной Студии для входа на сервер Студии. Эталоны: contracts/server/fixtures (раздел 9.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

GitScopeName = Literal["git:read", "git:write"]
DeviceClientKind = Literal["desktop", "cli"]
DeviceStatusName = Literal["pending", "approved", "denied", "expired", "delivered"]
ProjectRoleName = Literal["reader", "reviewer", "editor", "owner"]


class GitServerInfo(StrictModel):
    server: Literal["hse-doc-studio"]
    version: str
    device_flow: bool
    api: str


class GitWhoamiUser(StrictModel):
    id: str
    name: str
    email: str


class GitWhoamiToken(StrictModel):
    id: str
    name: str
    expires_at: datetime | None


class GitWhoami(StrictModel):
    user: GitWhoamiUser
    scopes: list[GitScopeName]
    token: GitWhoamiToken


class GitProject(StrictModel):
    id: str
    name: str
    owner_name: str
    role: ProjectRoleName
    can_push: bool
    clone_url: str
    updated_at: datetime | None


class GitProjectPage(StrictModel):
    items: list[GitProject]
    total: int
    limit: int
    offset: int


class DeviceCodeRequest(StrictModel):
    client_name: str = Field(min_length=1, max_length=128)
    client_kind: DeviceClientKind
    scopes: list[GitScopeName] = Field(min_length=1, max_length=2)


class DeviceCodeResponse(StrictModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class DeviceTokenRequest(StrictModel):
    device_code: str = Field(min_length=1, max_length=128)


class DeviceTokenResponse(StrictModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
    scope: str


class DeviceTokenError(StrictModel):
    error: Literal["authorization_pending", "slow_down", "access_denied", "expired_token"]


class DeviceAuthorizationInfo(StrictModel):
    user_code: str
    client_name: str
    client_kind: DeviceClientKind
    requested_scopes: list[GitScopeName]
    granted_scopes: list[GitScopeName] | None
    client_ip: str | None
    requested_at: datetime
    expires_at: datetime
    status: DeviceStatusName


class DeviceDecisionRequest(StrictModel):
    decision: Literal["approve", "deny"]
    scopes: list[GitScopeName] = Field(max_length=2)


class ProjectGitRemote(StrictModel):
    enabled: bool
    clone_url: str | None
    can_push: bool
    branch: str | None


class GitServerLoginRequest(StrictModel):
    server_url: str = Field(min_length=1, max_length=2048)
    client_name: str = Field(min_length=1, max_length=128)


class GitServerLogin(StrictModel):
    login_id: str
    server_url: str
    state: Literal["pending", "approved", "denied", "expired", "error"]
    user_code: str | None
    verification_uri_complete: str | None
    expires_at: datetime | None
    credential_id: str | None
    code: str | None


class GitServerItem(StrictModel):
    credential_id: str
    server_url: str
    host: str
    account_name: str | None
    scopes: list[GitScopeName]
    expires_at: datetime | None
    state: Literal["ok", "expired", "revoked", "unreachable"]


class GitServerList(StrictModel):
    items: list[GitServerItem]
