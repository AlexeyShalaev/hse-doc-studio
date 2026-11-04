---
title: Who is in the project now
description: Avatars of members in the project header, where they are working now, jumping to their document, collaborators' cursors and what others can see.
tags:
  - Workbench
  - Access
---

# Who is in the project now

<p class="hds-lede">On a shared server the project header shows which members are here right now and which document they are working on. Click an avatar to jump to the same document. Inside the document, collaborators' cursors carry their names.</p>

## Avatars in the header

To the left of the Studio badge you see round avatars of everyone who has the project open in a browser or whose local Studio is online with this project. An avatar shows initials, a green dot means “online”. Your own avatar has a ring. While nobody but you is in the project, there are no avatars.

- **Colour.** Every person has one colour everywhere: the avatar in the header and their cursor in the document match.
- **Label.** Hover an avatar or focus it with Tab: name, project role, where the person is now and where they work from.
- **Where now.** “is editing “Proposal””, “is viewing “Proposal””, “is viewing the findings of “Proposal””, “is building “Proposal””, “is in the project” (not in a document, for example in settings or submission), “is working locally” (the local Studio only).
- **From where.** “In the browser”, “in the local Studio” or both. Others never see the computer name, version or anything else about the machine.
- **Many people.** Five avatars and “+N” are shown; the full list opens from “+N” or the arrow next to it.
- **One icon per person.** If a person has several tabs open they are shown once, with the place from the freshest tab.

## Go to the document

Click an avatar or a row in the list (“Go to the document”) to open the document the person is working on. You land in the document, not at the spot where their cursor is. There is no button on your own avatar, on a person without a document or on someone working locally.

The list works with the keyboard: Tab moves, Enter goes, Esc closes it.

## Who sees this

Project members only. A reader and a reviewer see the same list, because the project's document names are already open to them. A guest and a person who opened the project through a share link do not see the list and do not appear in it. A person's private areas (settings, account, chats) never appear: only a project document and the mode are reported.

A person with the project open appears within a minute and disappears at once when they close the tab. If a tab vanishes without leaving (network failure), the person leaves the list after three minutes. If access is revoked, the person disappears from the list within twenty seconds.

## Cursors in the document

When you and a collaborator have the same file open, in source or in visual mode, you see their cursor and selection in their colour. A name label appears for a few seconds when the cursor shows up or moves, then fades; hover the cursor to see the name again. Without the right to edit you still see others' cursors but cannot type.

## For administrators

The people list uses the same signals and “online” window as connected Studios: `HSE_STUDIO__DEVICES__INTERVAL_S` and `HSE_STUDIO__DEVICES__ONLINE_WINDOW_S` ([reference](../deploy/env-reference.md)). A tab sends one short request a minute; the server keeps the signal in process memory and writes nothing to the database or the audit log. Details and the load estimate: `docs/design/connected-devices.md`, section 15.
