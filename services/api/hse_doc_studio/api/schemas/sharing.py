"""Контракт ссылок доступа, гостевых сессий и политики общего доступа (contracts/server, раздел links).

Эталоны: `contracts/server/fixtures/{ShareLink,ShareLinkList,...}`; их же разбирают zod-схемы
`entities/share-link`. Модели строгие: лишнее поле означает расхождение сторон.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.session import SettingState

LinkRoleName = Literal["reader", "reviewer", "editor"]
LinkStateName = Literal["active", "expired", "revoked", "blocked"]
LinkBlockReasonName = Literal["links_disabled", "org_links_off", "org_role_cap", "nda"]
LinkPreviewStateName = Literal["ok", "password_required", "login_required", "org_only", "inactive"]
OrgLinksModeName = Literal["any", "org_only", "off"]


class ShareLinkAuthor(StrictModel):
    id: str
    name: str


class ShareLinkVisitSummary(StrictModel):
    visitors: int
    opens: int
    last_at: datetime | None


class ShareLink(StrictModel):
    id: str
    label: str
    role: LinkRoleName
    show_sources: bool
    require_login: bool
    has_password: bool
    # Полный адрес ссылки: есть только у действующей и заблокированной политикой.
    url: str | None
    token_prefix: str
    # Автор скрыт (null) у редактора: он видит только свои ссылки.
    created_by: ShareLinkAuthor | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    state: LinkStateName
    blocked_reason: LinkBlockReasonName | None
    editable: bool
    visits: ShareLinkVisitSummary


class ShareLinkList(StrictModel):
    items: list[ShareLink]
    can_create: bool
    max_role: LinkRoleName
    # Вход по ссылке обязателен политикой (NDA или «только участникам организации»).
    forced_login: bool
    revoked_count: int


class CreateShareLinkRequest(StrictModel):
    label: str = Field(max_length=512)
    role: LinkRoleName
    show_sources: bool = False
    require_login: bool = False
    password: str | None = Field(default=None, max_length=512)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class UpdateShareLinkRequest(StrictModel):
    label: str | None = Field(default=None, max_length=512)
    role: LinkRoleName | None = None
    show_sources: bool | None = None
    require_login: bool | None = None
    password: str | None = Field(default=None, max_length=512)
    clear_password: bool = False
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    clear_expiry: bool = False


class ShareLinkVisit(StrictModel):
    visitor_kind: Literal["guest", "user"]
    name: str | None
    first_at: datetime
    last_at: datetime
    opens: int


class ShareLinkVisitPage(StrictModel):
    items: list[ShareLinkVisit]
    total: int
    limit: int
    offset: int


class ShareLinkPreview(StrictModel):
    state: LinkPreviewStateName
    project_name: str | None
    owner_name: str | None
    role: LinkRoleName | None
    show_sources: bool
    guest_name_required: bool
    signed_in: bool


class OpenShareLinkRequest(StrictModel):
    password: str | None = Field(default=None, max_length=512)
    guest_name: str | None = Field(default=None, max_length=256)


class OpenShareLinkResponse(StrictModel):
    project_id: str
    mode: Literal["guest", "user"]
    role: LinkRoleName
    show_sources: bool
    # Куда вести: рабочая область или просмотр PDF (читатель без исходников).
    landing: Literal["workspace", "view"]


class GuestLinkInfo(StrictModel):
    project_id: str
    project_name: str
    link_label: str
    role: LinkRoleName
    show_sources: bool


class GuestInfo(StrictModel):
    name: str | None
    links: list[GuestLinkInfo]


class UpdateGuestSessionRequest(StrictModel):
    name: str = Field(max_length=256)


class OrgSharingPolicy(StrictModel):
    links: OrgLinksModeName
    max_link_role: LinkRoleName
    nda_public_links: bool
    external_invites: bool
    # Ответ: может ли смотрящий править (владелец или админ организации); в запросе игнорируется.
    editable: bool = False


class AdminSharingSettings(StrictModel):
    links_enabled: bool
    max_link_role: LinkRoleName
    project_invites_allow_signup: bool
    fields: dict[str, SettingState]


class UpdateAdminSharingRequest(StrictModel):
    links_enabled: bool | None = None
    max_link_role: LinkRoleName | None = None
    project_invites_allow_signup: bool | None = None
