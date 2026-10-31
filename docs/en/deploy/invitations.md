---
title: Invitations and access requests
description: How to invite a person to a project on the server, how they accept, how to request access to a closed project and hand a project over to a new owner.
tags:
  - Deployment
  - Collaboration
---

# Invitations and access requests

<p class="hds-lede">On a shared server a new person joins a project only through an invitation: access starts once they click “Accept” themselves. Groups and organizations are still added right away.</p>

## Invite a person

1. Open the project, then **Project settings → People**.
2. In “Add”, find the person and click **Invite**, or click **Invite by email** if they are not in the list.
3. Pick a role, optionally a persona (an author, the supervisor), an expiry (1, 7, 14 or 30 days) and write a message.

| Situation | What the inviter sees |
|---|---|
| The person already has an account | “The invitation is in …'s Inbox”; with email configured a letter goes out too |
| Email is configured | “Invitation sent by email” |
| Email is not configured | a dialog with the invitation link: send it yourself |

The project owner and editors with “Can share” can invite. The invitation cannot grant more than the inviter has.

Pending invitations are listed under **Pending**, where you can resend them (at most once every 10 minutes) or revoke them.

!!! note "Direct add"
    An organization admin can add a member of that organization to an organization project right away with **Add now**. Changing the role of someone already added is immediate too.

## Accept an invitation

- Invitations arrive in the **Inbox** (the bell in the header). **Accept** opens the project.
- The email link opens without signing in. Only an account with the confirmed address the invitation was sent to can accept it, so a forwarded link does not work for someone else.
- In the “invite only” registration mode the email link lets the person sign up (unless the administrator turned this off); with registration closed, a person without an account cannot be invited.

## Request access

When a project is not available, the page offers **Request access** with a message. The answer is always the same: “If the project exists, its owner will be notified”. The owner approves the request with a role or denies it. After a denial the same project can be requested again in 7 days.

## Transfer a project

**Project settings → Danger zone → Transfer project**: to a person (they confirm in the Inbox within 7 days, you become an editor) or to an organization where you are an owner or admin (applies at once after typing the project name).

## For the administrator

| Instance key | Environment | Default | Meaning |
|---|---|---|---|
| `registration.project_invites_allow_signup` | `HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP` | `true` | in the “invite only” mode a project invitation lets the person sign up |

Inbox notifications are kept for 90 days. Emails go out only for invitations, access requests and transfers, when SMTP is configured.
