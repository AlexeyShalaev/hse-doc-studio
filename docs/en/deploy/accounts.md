---
title: People and sign-in
description: Registration modes, approval, invitations, mail, single sign-on via OIDC, passkey sign-in, password reset and sessions.
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

The Mail section in the admin area, or `HSE_STUDIO__MAIL__*`. The SMTP password is accepted on write and never returned. The test mail button sends a message to the administrator's account address. Mail goes through an outbox queue, so an SMTP failure does not lose a message. Which emails are sent, in which language and how they look: [Server emails](mail.md).

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

## Passkey sign-in

A passkey is a sign-in key kept on a device (Touch ID, Face ID, Windows Hello, a phone, a hardware key) or in a password manager. The private part of the key never leaves the device, the server only stores the public part. Passkeys are added next to the password and single sign-on, they do not replace them.

### How a person uses it

1. Settings → Account → the Passkeys card → Add a passkey. If you signed in more than 10 minutes ago, the Studio asks you to confirm it's you: with your password, a passkey you already added, or a new single sign-on.
2. The browser offers to save the key. The key name comes from the device (for example "Chrome · macOS"), you can change it.
3. On the sign-in screen: press "Sign in with a passkey" or pick the key in the suggestions of the email field. No address or password needed.
4. A key is removed from the same card (also after confirming it's you). The last way to sign in cannot be removed: set a password or link single sign-on first.

A person invited to their own address can create the account with a passkey right away, without a password: the invitation page has a "Create account with a passkey" button. A password can be set later with "Forgot your password?". An invitation without an address still uses sign-up with a password.

The Studio mails the person when a passkey is added and when an administrator resets their keys (if SMTP is configured; without it the event is only in the audit log).

A key marked "does not work at this address" was created for a previous server address: remove it and add a new one.

### What the administrator configures

| Where | What |
|---|---|
| Admin → Sign-in → Passkey sign-in | allow or forbid; `HSE_STUDIO__AUTH__PASSKEYS_ENABLED` sets the value from the environment and locks editing |
| `HSE_STUDIO__AUTH__PUBLIC_URL` | the Studio address: the key domain comes from it. HTTPS is required (or `http://localhost` for a test stand) and a domain name, not an IP address |
| `HSE_STUDIO__AUTH__PASSKEY_RP_ID` | optional: a parent key domain (`example.org` for `studio.example.org`) so that keys survive a move between subdomains |
| Admin → People | the Passkeys column: how many keys the person has |
| Admin → People → person card | how many keys the person has and when they were used; "Reset passkeys" removes all of the person's keys (sessions stay open) |

!!! warning "Keys are bound to the domain"
    A browser uses a key only on the domain it was created for. If you change the server address (`public_url`), existing keys stop working and people have to add new ones. The admin area shows how many keys are bound to each domain and warns about keys of another domain. To keep keys working across subdomains, set `PASSKEY_RP_ID` to the common parent domain in advance.

Behind a reverse proxy the domain and origin come from `public_url`, not from request headers: make sure it is set. If the address does not fit (no `public_url`, plain HTTP outside localhost, an IP address), passkeys are unavailable and the admin area names the reason.

Passkey sign-in requires user verification on the device (biometrics or a PIN): a key without a PIN does not open an account. The Studio does not ask for authenticator model details (attestation `none`). If a key reports a signature counter lower than before (a sign of a cloned key), the sign-in is refused and written to the audit log.

A person lost a device: reset their passkeys in the person card and end their sessions if needed. If no other way to sign in is left, issue a password reset link.

The local Studio has no sign-in, so passkeys are not used there.

## Users

In the People section: search, disable and enable, and end all of a user's sessions.

Sessions: an opaque identifier in an HttpOnly cookie, a sliding 7-day idle limit and a 30-day cap (`SESSION_IDLE_DAYS`, `SESSION_ABSOLUTE_DAYS`). Passwords are stored as argon2id and must be at least 10 characters.

### Password reset

Users reset their own password by mail. If mail is unavailable, the administrator can issue a reset link. This is **break-glass**: it needs confirmation, is written to the audit log, and the user gets a notification mail. The action does not give the administrator access to the user's projects, but they could then sign in with the new password, so use it as a last resort.

## Audit

The Audit section keeps sign-in events (including passkey sign-ins with the refusal reason), passkey additions, removals and resets, permission changes, reset links, runner actions and settings changes. Retention: `HSE_STUDIO__SERVER__AUDIT_RETENTION_DAYS` (365 by default, 0 means forever).

## Access tokens

Users issue personal tokens in account settings for the CLI and scripts. A token is shown once, only its hash is stored. A token cannot manage tokens and is exempt from the CSRF check.
