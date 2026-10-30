---
title: People and sign-in
description: Registration modes, approval, invitations, mail, single sign-on via OIDC, password reset and sessions.
tags:
  - Deployment
  - Administration
---

# People and sign-in

<p class="hds-lede">Everything below is configured in the admin area (`/admin`) or with environment variables. A value set in the environment locks editing in the UI.</p>

## Registration modes

| Mode | Who can register |
|---|---|
| `open` | anyone who can reach the address |
| `domains` | only mail addresses from the domain list |
| `invite` | only by invitation |
| `closed` | nobody; the administrator creates accounts |

On top of any mode you can require **approval**: a new account waits for an administrator decision in the Approvals section and cannot sign in before that.

Environment: `HSE_STUDIO__AUTH__REGISTRATION_MODE`, `..._REGISTRATION_DOMAINS`, `..._REQUIRE_APPROVAL`, `..._PASSWORD_ENABLED`.

## Invitations

The administrator enters an address and the Studio sends a mail with a link. An invitation can be resent or revoked. Without configured mail, invitations are not delivered.

## Mail (SMTP)

The Mail section in the admin area, or `HSE_STUDIO__MAIL__*`. The SMTP password is accepted on write and never returned. The test mail button sends a message to the administrator's account address. Mail goes through an outbox queue, so an SMTP failure does not lose a message.

Mail is needed for invitations, address confirmation and password reset.

## Single sign-on (OIDC)

In the Sign-in section add a provider:

| Field | Value |
|---|---|
| Label | text on the sign-in button |
| Issuer | provider address, used to find `/.well-known/openid-configuration` |
| Client ID, Client secret | issued by the provider; the secret is stored encrypted and never shown |
| Scopes | `openid email profile` by default |
| Auto-provision | create an account on first sign-in |

!!! note "Status"
    Provider setup is already in the admin area. The provider sign-in flow itself is enabled with the final stage 2 slice; check the release notes of the version where it started working for the redirect URI to register with the provider and how existing accounts are linked.

Password sign-in can be turned off (`password_enabled`) only when at least one provider is enabled; otherwise nobody could sign in.

If the provider lives on an internal network, add its host to `HSE_STUDIO__EGRESS__ALLOWLIST`: outgoing requests to private addresses are blocked by default.

## Users

In the People section: search, disable and enable, and end all of a user's sessions.

Sessions: an opaque identifier in an HttpOnly cookie, a sliding 7-day idle limit and a 30-day cap (`SESSION_IDLE_DAYS`, `SESSION_ABSOLUTE_DAYS`). Passwords are stored as argon2id and must be at least 10 characters.

### Password reset

Users reset their own password by mail. If mail is unavailable, the administrator can issue a reset link. This is **break-glass**: it needs confirmation, is written to the audit log, and the user gets a notification mail. The action does not give the administrator access to the user's projects, but they could then sign in with the new password, so use it as a last resort.

## Audit

The Audit section keeps sign-in events, permission changes, reset links, runner actions and settings changes. Retention: `HSE_STUDIO__SERVER__AUDIT_RETENTION_DAYS` (365 by default, 0 means forever).

## Access tokens

Users issue personal tokens in account settings for the CLI and scripts. A token is shown once, only its hash is stored. A token cannot manage tokens and is exempt from the CSRF check.
