"""Чистые правила приглашений: внешний домен и разбор политики организации."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.core.identity.normalize import email_domain, normalize_domain


def external_invites_allowed(policies: Mapping[str, object]) -> bool:
    """`sharing.external_invites` из `orgs.policies`; без ключа и при мусоре приглашать можно (по умолчанию true)."""
    sharing = policies.get("sharing")
    if not isinstance(sharing, Mapping):
        return True
    value = sharing.get("external_invites", True)
    return value if isinstance(value, bool) else True


def org_domains(policies: Mapping[str, object]) -> frozenset[str]:
    """Домены организации (`domains`, заполняются из SSO); пусто, если организация их не знает."""
    raw = policies.get("domains")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(normalize_domain(d) for d in raw if isinstance(d, str) and d.strip())


def email_allowed_for_org(policies: Mapping[str, object], email: str) -> bool:
    """Почта вне доменов организации запрещена только при `external_invites = false` и известных доменах."""
    if external_invites_allowed(policies):
        return True
    domains = org_domains(policies)
    return not domains or email_domain(email) in domains
