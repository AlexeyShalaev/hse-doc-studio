"""Политика ссылок доступа: установка (`instance_settings`) и организация (`orgs.policies`).

Чистые функции: разбор политики организации с умолчаниями, итог установки и организации, состояние ссылки
по текущей политике, предел роли новой ссылки. Политика пересчитывается на каждый запрос.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.links import LinkBlockReason, LinkRole, LinkState, ShareLink
from hse_doc_studio.core.access.resolution import ROLE_ORDER

POLICY_VERSION = 1
KEY_LINKS_ENABLED = "sharing.links_enabled"
KEY_MAX_LINK_ROLE = "sharing.max_link_role"
KEY_PROJECT_INVITES_ALLOW_SIGNUP = "registration.project_invites_allow_signup"
SHARING_KEYS = (KEY_LINKS_ENABLED, KEY_MAX_LINK_ROLE, KEY_PROJECT_INVITES_ALLOW_SIGNUP)


class OrgLinksMode(StrEnum):
    any = "any"
    org_only = "org_only"
    off = "off"


@dataclass(frozen=True)
class InstanceSharing:
    links_enabled: bool = True
    max_link_role: LinkRole = LinkRole.editor
    project_invites_allow_signup: bool = True


@dataclass(frozen=True)
class OrgSharing:
    links: OrgLinksMode = OrgLinksMode.any
    max_link_role: LinkRole = LinkRole.editor
    nda_public_links: bool = False
    external_invites: bool = True


@dataclass(frozen=True)
class SharingPolicy:
    """Итог установки и организации для одного проекта."""

    links_enabled: bool = True
    org_mode: OrgLinksMode = OrgLinksMode.any
    max_link_role: LinkRole = LinkRole.editor
    nda_public_links: bool = False
    external_invites: bool = True


@dataclass(frozen=True)
class SharingEnvOverrides:
    """Значения окружения: заданное (не None) побеждает БД и в интерфейсе только для чтения."""

    links_enabled: bool | None = None
    max_link_role: LinkRole | None = None
    project_invites_allow_signup: bool | None = None

    def locked_keys(self) -> frozenset[str]:
        pairs = (
            (KEY_LINKS_ENABLED, self.links_enabled),
            (KEY_MAX_LINK_ROLE, self.max_link_role),
            (KEY_PROJECT_INVITES_ALLOW_SIGNUP, self.project_invites_allow_signup),
        )
        return frozenset(key for key, value in pairs if value is not None)


def _rank(role: LinkRole | Role) -> int:
    return ROLE_ORDER.index(Role(role.value))


def _link_role(raw: object, default: LinkRole) -> LinkRole:
    try:
        return LinkRole(raw) if isinstance(raw, str) else default
    except ValueError:
        return default


def _flag(raw: object, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def parse_org_sharing(policies: Mapping[str, object] | None) -> OrgSharing:
    """Блок `sharing` из `orgs.policies`; отсутствующие и негодные значения берут умолчания."""
    defaults = OrgSharing()
    block = (policies or {}).get("sharing")
    if not isinstance(block, Mapping):
        return defaults
    raw_mode = block.get("links")
    try:
        mode = OrgLinksMode(raw_mode) if isinstance(raw_mode, str) else defaults.links
    except ValueError:
        mode = defaults.links
    return OrgSharing(
        links=mode,
        max_link_role=_link_role(block.get("max_link_role"), defaults.max_link_role),
        nda_public_links=_flag(block.get("nda_public_links"), defaults.nda_public_links),
        external_invites=_flag(block.get("external_invites"), defaults.external_invites),
    )


def dump_org_sharing(policies: Mapping[str, object] | None, sharing: OrgSharing) -> dict[str, object]:
    """`orgs.policies` с новым блоком `sharing`; прочие ключи сохраняются."""
    result = dict(policies or {})
    result["version"] = POLICY_VERSION
    result["sharing"] = {
        "links": sharing.links.value,
        "max_link_role": sharing.max_link_role.value,
        "nda_public_links": sharing.nda_public_links,
        "external_invites": sharing.external_invites,
    }
    return result


def effective_instance_sharing(values: Mapping[str, object], env: SharingEnvOverrides) -> InstanceSharing:
    defaults = InstanceSharing()
    return InstanceSharing(
        links_enabled=env.links_enabled
        if env.links_enabled is not None
        else _flag(values.get(KEY_LINKS_ENABLED), defaults.links_enabled),
        max_link_role=env.max_link_role or _link_role(values.get(KEY_MAX_LINK_ROLE), defaults.max_link_role),
        project_invites_allow_signup=env.project_invites_allow_signup
        if env.project_invites_allow_signup is not None
        else _flag(values.get(KEY_PROJECT_INVITES_ALLOW_SIGNUP), defaults.project_invites_allow_signup),
    )


def effective_policy(instance: InstanceSharing, org: OrgSharing | None) -> SharingPolicy:
    """Для личного проекта (`org` None) действует только политика установки."""
    if org is None:
        return SharingPolicy(links_enabled=instance.links_enabled, max_link_role=instance.max_link_role)
    cap = min(instance.max_link_role, org.max_link_role, key=_rank)
    return SharingPolicy(
        links_enabled=instance.links_enabled,
        org_mode=org.links,
        max_link_role=cap,
        nda_public_links=org.nda_public_links,
        external_invites=org.external_invites,
    )


def login_forced(policy: SharingPolicy, *, project_nda: bool) -> bool:
    """Ссылка обязана требовать вход: организация пускает только своих или проект под NDA без публичных ссылок."""
    return policy.org_mode is OrgLinksMode.org_only or (project_nda and not policy.nda_public_links)


def link_state(  # noqa: PLR0911 — по ветке на каждое состояние и причину
    link: ShareLink, now: datetime, policy: SharingPolicy, *, project_nda: bool
) -> tuple[LinkState, LinkBlockReason | None]:
    if link.revoked_at is not None:
        return LinkState.revoked, None
    if link.expires_at is not None and link.expires_at <= now:
        return LinkState.expired, None
    if not policy.links_enabled:
        return LinkState.blocked, LinkBlockReason.links_disabled
    if policy.org_mode is OrgLinksMode.off:
        return LinkState.blocked, LinkBlockReason.org_links_off
    if _rank(link.role) > _rank(policy.max_link_role):
        return LinkState.blocked, LinkBlockReason.org_role_cap
    if project_nda and not policy.nda_public_links and not link.require_login:
        return LinkState.blocked, LinkBlockReason.nda
    return LinkState.active, None


def link_usable(link: ShareLink, now: datetime, policy: SharingPolicy, *, project_nda: bool) -> bool:
    """Ссылка действует для вошедшего (ограничение `org_only` по участию проверяет вызывающий).

    Ссылка без входа на NDA-проекте закрыта для гостя, но вошедшего она по-прежнему пускает.
    """
    state, reason = link_state(link, now, policy, project_nda=project_nda)
    return state is LinkState.active or reason is LinkBlockReason.nda


def guest_may_use(link: ShareLink, policy: SharingPolicy, *, project_nda: bool) -> bool:
    """Гость (без входа) проходит, только если ссылка и политика не требуют входа."""
    return not link.require_login and not login_forced(policy, project_nda=project_nda)


def cap_role(requested: LinkRole, *, creator: Role, policy: SharingPolicy) -> LinkRole | None:
    """None, если запрошенная роль выше роли создателя или предела политики."""
    if _rank(requested) > _rank(creator) or _rank(requested) > _rank(policy.max_link_role):
        return None
    return requested


def max_role_for(creator: Role, policy: SharingPolicy) -> LinkRole:
    """Старшая роль, которую создатель может дать ссылкой."""
    creator_cap = LinkRole.editor if creator in (Role.editor, Role.owner) else LinkRole(creator.value)
    return min(creator_cap, policy.max_link_role, key=_rank)


class ISharingPolicyReader(Protocol):
    async def for_project(self, project_id: UUID) -> SharingPolicy: ...

    async def instance(self) -> SharingPolicy: ...


class DefaultSharingPolicyReader:
    """Значения по умолчанию: подставляется там, где хранилища политики нет (локальный режим, тесты)."""

    async def for_project(self, project_id: UUID) -> SharingPolicy:  # noqa: ARG002
        return SharingPolicy()

    async def instance(self) -> SharingPolicy:
        return SharingPolicy()
