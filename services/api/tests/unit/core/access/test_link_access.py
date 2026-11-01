"""Ссылки доступа в политике: гость и ссылочное право, сборка права со ссылкой, политика организации и установки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.actions import GUEST_DENIED, LINK_DENIED, ROLE_ACTIONS, Action
from hse_doc_studio.core.access.entities import Actor, ActorSource, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.links import (
    LinkBlockReason,
    LinkRole,
    LinkState,
    ShareLink,
    clean_text,
    hash_secret,
    looks_like_link_token,
    new_link_token,
    password_delay_s,
    token_prefix_of,
)
from hse_doc_studio.core.access.policy import Decision, decide, required_role
from hse_doc_studio.core.access.repositories import ProjectMemberGrant
from hse_doc_studio.core.access.resolution import LinkGrant, resolve_grant
from hse_doc_studio.core.access.sharing_policy import (
    InstanceSharing,
    OrgLinksMode,
    OrgSharing,
    SharingEnvOverrides,
    SharingPolicy,
    cap_role,
    dump_org_sharing,
    effective_instance_sharing,
    effective_policy,
    guest_may_use,
    link_state,
    link_usable,
    login_forced,
    max_role_for,
    parse_org_sharing,
)

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
USER = Actor.user("u1", "Вера")


def _guest_acl(role: Role, *, show_sources: bool = False) -> tuple[Actor, ProjectAcl]:
    guest = Actor.guest("gs_1", "Борис", link_id="lnk_1")
    grant = Grant(role=role, show_sources=show_sources or role is not Role.reader, link_id="lnk_1")
    return guest, ProjectAcl(project_id="p", owner_id="o", grants={guest.key or "": grant})


def test__actor_guest__key_and_source() -> None:
    guest = Actor.guest("gs_abc", "Борис")

    assert guest.key == "guest:gs_abc"
    assert guest.id == "gs_abc"
    assert guest.source is ActorSource.link
    assert guest.link_id is None
    assert guest.with_link("lnk_1").link_id == "lnk_1"
    assert guest.with_link("lnk_1").key == guest.key


def test__grant__via_link() -> None:
    assert Grant(Role.reader, link_id="lnk").via_link
    assert not Grant(Role.reader).via_link


def test__link_denied__is_guest_denied_without_agent() -> None:
    assert GUEST_DENIED - {Action.AGENT_USE} == LINK_DENIED
    assert Action.SHARE in LINK_DENIED


@pytest.mark.parametrize("role", [Role.reader, Role.reviewer, Role.editor])
@pytest.mark.parametrize("action", list(Action))
def test__guest_matrix__role_minus_guest_denied(role: Role, action: Action) -> None:
    guest, acl = _guest_acl(role)
    path = "main.tex" if action in {Action.FILES_WRITE, Action.FILES_READ} else None
    if action in {Action.FILES_READ, Action.SOURCES_READ}:
        # Исходники у ссылки «Читатель» только по флагу; у Рецензента и Редактора всегда.
        expected = role is not Role.reader
    else:
        expected = action in ROLE_ACTIONS[role] and action not in GUEST_DENIED

    assert (decide(guest, action, acl, path) is Decision.allow) is expected


@pytest.mark.parametrize("action", sorted(LINK_DENIED))
def test__signed_in_link_grant__link_denied_forbidden(action: Action) -> None:
    acl = ProjectAcl(project_id="p", grants={"u1": Grant(Role.editor, show_sources=True, link_id="lnk")})

    assert decide(USER, action, acl) is Decision.forbidden
    assert required_role(USER, action, acl) is None


def test__signed_in_link_grant__agent_allowed_for_editor() -> None:
    acl = ProjectAcl(project_id="p", grants={"u1": Grant(Role.editor, show_sources=True, link_id="lnk")})

    assert decide(USER, Action.AGENT_USE, acl) is Decision.allow
    assert decide(USER, Action.FILES_WRITE, acl, "main.tex") is Decision.allow


def test__guest_agent__forbidden_even_for_editor() -> None:
    guest, acl = _guest_acl(Role.editor)

    assert decide(guest, Action.AGENT_USE, acl) is Decision.forbidden
    assert decide(guest, Action.BUILD_RUN, acl) is Decision.allow


def test__reader_link_without_sources__only_output() -> None:
    guest, acl = _guest_acl(Role.reader)

    assert decide(guest, Action.FILES_READ, acl, "output/thesis.pdf") is Decision.allow
    assert decide(guest, Action.FILES_READ, acl, "main.tex") is Decision.forbidden
    guest, acl = _guest_acl(Role.reader, show_sources=True)
    assert decide(guest, Action.FILES_READ, acl, "main.tex") is Decision.allow


def test__resolve_grant__membership_beats_higher_link() -> None:
    direct = ProjectMemberGrant("user", "u1", Role.reader, show_sources=False)
    link = LinkGrant("lnk", Role.editor, show_sources=True)

    grant = resolve_grant(is_owner=False, direct=direct, links=[link])

    assert grant is not None
    assert grant.role is Role.reader
    assert not grant.via_link


def test__resolve_grant__link_only__flags() -> None:
    grant = resolve_grant(is_owner=False, direct=None, links=[LinkGrant("lnk", Role.reviewer, show_sources=False)])

    assert grant == Grant(role=Role.reviewer, show_sources=True, link_id="lnk")


def test__resolve_grant__several_links__highest_then_first() -> None:
    links = [
        LinkGrant("new_reader", Role.reader, show_sources=False),
        LinkGrant("new_editor", Role.editor, show_sources=False),
        LinkGrant("old_editor", Role.editor, show_sources=False),
    ]

    grant = resolve_grant(is_owner=False, direct=None, links=links)

    assert grant is not None
    assert grant.link_id == "new_editor"
    assert grant.can_share is False


def _link(**extra: object) -> ShareLink:
    values: dict[str, object] = {
        "id": "lnk_1",
        "project_id": uuid4(),
        "label": "Для научрука",
        "role": LinkRole.reader,
        "show_sources": False,
        "require_login": False,
        "has_password": False,
        "token_prefix": "abcdefgh",
        "created_by": "u1",
        "created_at": NOW,
        "updated_at": NOW,
        "expires_at": None,
        "revoked_at": None,
        "revoke_reason": None,
        "replaced_by": None,
        "last_opened_at": None,
    }
    values.update(extra)
    return ShareLink(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("link", "policy", "nda", "expected"),
    [
        (_link(), SharingPolicy(), False, (LinkState.active, None)),
        (_link(revoked_at=NOW, revoke_reason="manual"), SharingPolicy(), False, (LinkState.revoked, None)),
        (_link(expires_at=NOW), SharingPolicy(), False, (LinkState.expired, None)),
        (_link(), SharingPolicy(links_enabled=False), False, (LinkState.blocked, LinkBlockReason.links_disabled)),
        (_link(), SharingPolicy(org_mode=OrgLinksMode.off), False, (LinkState.blocked, LinkBlockReason.org_links_off)),
        (
            _link(role=LinkRole.editor),
            SharingPolicy(max_link_role=LinkRole.reviewer),
            False,
            (LinkState.blocked, LinkBlockReason.org_role_cap),
        ),
        (_link(), SharingPolicy(), True, (LinkState.blocked, LinkBlockReason.nda)),
        (_link(require_login=True), SharingPolicy(), True, (LinkState.active, None)),
        (_link(), SharingPolicy(nda_public_links=True), True, (LinkState.active, None)),
    ],
)
def test__link_state__each_reason(
    link: ShareLink, policy: SharingPolicy, nda: bool, expected: tuple[LinkState, LinkBlockReason | None]
) -> None:
    assert link_state(link, NOW, policy, project_nda=nda) == expected


def test__link_usable__nda_block_still_admits_signed_in() -> None:
    assert link_usable(_link(), NOW, SharingPolicy(), project_nda=True)
    assert not link_usable(_link(), NOW, SharingPolicy(org_mode=OrgLinksMode.off), project_nda=False)
    assert not link_usable(_link(expires_at=NOW - timedelta(days=1)), NOW, SharingPolicy(), project_nda=False)


def test__guest_may_use__login_and_policy() -> None:
    assert guest_may_use(_link(), SharingPolicy(), project_nda=False)
    assert not guest_may_use(_link(require_login=True), SharingPolicy(), project_nda=False)
    assert not guest_may_use(_link(), SharingPolicy(org_mode=OrgLinksMode.org_only), project_nda=False)
    assert not guest_may_use(_link(), SharingPolicy(), project_nda=True)
    assert login_forced(SharingPolicy(), project_nda=True)
    assert not login_forced(SharingPolicy(nda_public_links=True), project_nda=True)


def test__cap_role__creator_and_policy() -> None:
    policy = SharingPolicy(max_link_role=LinkRole.reviewer)

    assert cap_role(LinkRole.reader, creator=Role.editor, policy=policy) is LinkRole.reader
    assert cap_role(LinkRole.editor, creator=Role.owner, policy=policy) is None
    assert cap_role(LinkRole.editor, creator=Role.reviewer, policy=SharingPolicy()) is None
    assert max_role_for(Role.owner, policy) is LinkRole.reviewer
    assert max_role_for(Role.editor, SharingPolicy()) is LinkRole.editor


@pytest.mark.parametrize(
    ("policies", "expected"),
    [
        (None, OrgSharing()),
        ({}, OrgSharing()),
        ({"sharing": "junk"}, OrgSharing()),
        ({"sharing": {"links": "nope", "max_link_role": "owner", "nda_public_links": "yes"}}, OrgSharing()),
        (
            {"version": 1, "sharing": {"links": "org_only", "max_link_role": "reviewer", "external_invites": False}},
            OrgSharing(links=OrgLinksMode.org_only, max_link_role=LinkRole.reviewer, external_invites=False),
        ),
    ],
)
def test__parse_org_sharing__defaults_for_missing_and_junk(policies: object, expected: OrgSharing) -> None:
    assert parse_org_sharing(policies) == expected  # type: ignore[arg-type]


def test__dump_org_sharing__keeps_other_keys_and_roundtrips() -> None:
    strict = OrgSharing(links=OrgLinksMode.off, max_link_role=LinkRole.reader, nda_public_links=True)

    dumped = dump_org_sharing({"other": 1}, strict)

    assert dumped["other"] == 1
    assert dumped["version"] == 1
    assert parse_org_sharing(dumped) == strict


def test__effective_policy__personal_project_uses_instance_only() -> None:
    instance = InstanceSharing(links_enabled=True, max_link_role=LinkRole.reviewer)

    assert effective_policy(instance, None) == SharingPolicy(max_link_role=LinkRole.reviewer)
    combined = effective_policy(instance, OrgSharing(links=OrgLinksMode.org_only, max_link_role=LinkRole.editor))
    assert combined.max_link_role is LinkRole.reviewer
    assert combined.org_mode is OrgLinksMode.org_only


def test__effective_instance_sharing__env_wins() -> None:
    stored = {"sharing.links_enabled": True, "sharing.max_link_role": "reviewer"}
    env = SharingEnvOverrides(links_enabled=False)

    result = effective_instance_sharing(stored, env)

    assert result == InstanceSharing(links_enabled=False, max_link_role=LinkRole.reviewer)
    assert env.locked_keys() == {"sharing.links_enabled"}
    assert effective_instance_sharing({"sharing.max_link_role": "owner"}, SharingEnvOverrides()) == InstanceSharing()


def test__token_helpers() -> None:
    token = new_link_token()

    assert token.startswith("hsl_")
    assert len(token) >= 40
    assert looks_like_link_token(token)
    assert not looks_like_link_token("hsl_short")
    assert token_prefix_of(token) == token[4:12]
    assert hash_secret(token) != hash_secret(new_link_token())


def test__clean_text_and_password_delay() -> None:
    assert clean_text("  Для\tнаучрука\n ", 128) == "Для научрука"
    assert clean_text("   ", 128) is None
    assert clean_text("x" * 129, 128) is None
    assert password_delay_s(9) == 0
    assert password_delay_s(10) == 1
    assert password_delay_s(40) == 15 * 60
