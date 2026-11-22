---
title: Send for review
description: The "Changes" panel of Template Studio: what you changed, the main button, the merge request, your own copy of the repository (a fork), hosting checks and the official templates.
tags:
  - Templates
  - Pack authors
---

# Send for review

<p class="hds-lede">Everything you changed and have not sent yet is collected in the "Changes" panel. For a space from a repository the edits go into a work branch and with a merge request (a request on the hosting: PR on GitHub, MR on GitLab) into the main one. The decision to merge is made by the repository maintainers, the Studio only prepares the proposal.</p>

## The "Changes" panel

The **Changes** button with a counter sits in the strip on every tab (on a phone it is a tab at the bottom). The panel opens on the right and shows:

- **What changed**: files by groups ("New version … and my edits", "Shared pack files", "Other files") under human names: "Version description", "Technical specification: terms", "Technical specification: text", "Check rules". If there are no changes the panel says so.
- **What changed for students and supervisors** and the release of the version: [Editing a copy and releasing](versions.md).
- **Checks**: template errors that prevent sending (the "Fix errors" button leads to "Check").
- **The state of the request**: "request #412 is open", checks are running or passed, the request is accepted or closed.
- At the bottom is the panel's **main button**: **Send for review**, **Update request** or **Retry** if a step failed (completed steps are not repeated).

The **More** menu of the panel holds what is needed rarely:

- **Save a point**: fix the edits in the work branch under your name without sending. If there is no branch yet the Studio creates it itself. The message is composed by the Studio from the changed versions.
- **Branch…**: a branch is the working line of your changes. Here you can create a new one with a name from the Studio, give your own name or switch to an existing one (only without unsaved edits).
- **Take news from the main branch**: add to your branch what appeared in the main one. If the main branch edits the same places, the merge is cancelled and the Studio names the files: fix them in your branch and take again.
- **Repository access**: checks the token and helps to issue a new one.
- **Open comparison on the hosting**.
- **Reset all my changes**: return the space to the fresh main branch. Unsaved edits are discarded only after confirmation; the branch and the request on the hosting stay as they are. After an accepted request the same action is called **Start a new edit**.

The main button of the strip repeats the next step while the panel is closed: **Describe changes**, **Fix errors**, **Send for review** or "Request #412 · checks are running". A space on a folder without git has no button: edits are written to the folder at once, with the caption "Saved to the folder".

## The merge request

**Send for review**:

1. The Studio checks the changed packs with the same code as `hse-doc-studio pack check --base`: the linter, immutability of released versions, schemas, the version number. Errors stop the sending and appear in "Check", "Issues"; other people's errors in untouched packs do not interfere.
2. The notes are written, the version is released (if the tick is set), the edits are committed, the branch goes to the hosting. What is being done now is shown as a list; the failed step is highlighted and the retry starts from it.
3. A merge request into the main branch is opened. You can write the title and description (the "Request title and description" section) or leave them to the Studio: it adds a summary to the description (versions, the size of changes, notes, check results, how many ready cases change). If a request from this branch is already open, the branch is just updated, and the button is called "Update request".

If the hosting did not let the request be opened through the API, there is a link to the request page on the hosting.

**No right to write to the repository.** The Studio offers **Send to my copy**: **Create my copy automatically** (GitHub) or **Enter my own copy** on the same server. Your own copy of the repository (a fork) is remembered for the space.

## Hosting checks { #hosting-checks }

After sending, the panel shows the status of the checks for the sent tip: GitHub (check runs and commit statuses) or GitLab (a pipeline, a token with `read_api` is needed). While the checks run the status refreshes every 30 seconds. **Checks on the hosting** expand a list with links. If the hosting does not give the status to this token, the link leads to the checks page.

A ready CI for your own packs repository: [Command line and CI](ci.md#ci).

## Official templates { #official }

The Studio's own templates live in its repository (`packs/`). Anyone with a GitHub account can send a fix to them:

1. In the list of spaces pick **Official HSE templates**, the **Start** button. Your GitHub token is needed: a classic one with the `public_repo` scope (your own copy of the repository, a branch in it and a request into a public repository). If there is no token the window gives a link to create one and a field to paste it into: the Studio checks the token, saves it under "Repository access" and selects it at once. The Studio downloads only the templates folder.
2. Edits and a copy of the version as usual.
3. **Send for review**: the branch goes to your copy of the repository (a fork), and the merge request is opened from your account. There are no other ways: there is no installation bot for the official templates, it is safer this way. Commits may touch only the templates folder.
4. Before the first sending tick the consent: the contribution is public and distributed under the repository license. The contribution rules: the "Contributing to the official packs" section of [CONTRIBUTING.md](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/CONTRIBUTING.md#contributing-to-the-official-packs).

For a request from a new contributor's copy GitHub does not run checks until a maintainer allows it. The Studio shows "Awaiting approval": that is not an error. Official templates ship with the Studio: after the request is merged the new version reaches users with the next release.
