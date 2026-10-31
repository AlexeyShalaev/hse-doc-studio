---
title: Link sharing
description: Project links for supervisors and co-authors without an invitation, guests, password, expiry, revocation and organization policy.
tags:
  - Workbench
  - Access
---

# Link sharing

<p class="hds-lede">A link opens a project on a shared server to someone without an invitation: a supervisor, a reviewer, a group. Whoever opens the link gets the chosen role. Revoke the link and access is gone.</p>

## Where to create a link

Project settings, the “Members” section, the “Link sharing” block. The owner and editors who may share can create links. An editor sees and changes only their own links; the owner sees all of them.

When creating a link, set the label, the role (Reader, Reviewer or Editor, never above your own role or the organization limit), whether a reader sees sources and history, whether sign-in is required, an optional password (8 to 128 characters) and the expiry.

## What the person who opens the link sees

- **Without signing in** the person becomes a guest. Reviewer and Editor links ask for a name, which history shows as “Guest: Boris (link “For the group”)”. Guests cannot use the agent, submission, signatures, git, project settings or access.
- **A reader without sources** sees the documents with the latest built PDF of each and can download it.
- **A signed-in user** finds the project in their list marked “By link”. Access lasts while the link is valid; membership always wins over a link.

## Reissue, revoke and visits

Reissue creates a new link with the same settings and stops the old one for everyone. Revoke closes access at once. Visits list who opened the link, when, and how many times.

## Organization and installation policy

Organization administrators choose whether links to organization projects are allowed, the highest role by link and whether NDA projects may open without sign-in. Installation administrators turn links on or off and set the overall role limit. Tightening the policy does not delete links: they stop working immediately and are marked “Inactive” in the list.
