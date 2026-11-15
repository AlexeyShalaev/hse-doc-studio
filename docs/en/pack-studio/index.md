---
title: Template Studio
description: What Template Studio is, how to open it and where it takes packs from: a folder on disk, your own git repository or the official Studio packs.
tags:
  - Templates
  - Pack authors
---

# Template Studio

<p class="hds-lede">Template Studio is the section for pack authors. There you edit a pack in an editor with checks, build a preview on sample data, place signatures with the mouse on the PDF, release a new template version and send the changes as a merge request. Students do not need it: they work with projects, not packs.</p>

How a pack, its versions and the patch, minor and major classes work: [Packs and templates](../reference/pack.md).

## How to open it

| Where | How to turn it on |
|---|---|
| Local Studio | **Settings**, the "Template Studio" section, the "Template author tools" switch. A header button appears. |
| Server | An administrator turns the section on in `/admin`, "Template Studio", and grants the "Template author" right to a person or a group. Installation administrators always have it. |
| Template Studio only, on your computer | A launch profile with one command, without sign-in or projects: [Template Studio on your computer](../deploy/pack-studio-local.md). |

The section lives at `/pack-studio`. Turning it on does not change projects.

## Workspaces

A workspace is the pack source you work with: where the Studio takes the files from and where it sends the edits. You can have several, each with its own file tree, branch and checks.

**New workspace**:

- **Folder on disk** (local only). The repository root or the packs folder itself. Edits go straight into the folder and there is no merge request: you commit and push yourself.
- **Git repository.** The repository address, the access, the base branch (empty: the server default branch) and the packs folder inside the repository (`packs`, "." means the root). The Studio clones only the packs folder; cloning takes up to a couple of minutes.

The repository access is a token from **Settings**, the "Repository access" section. The token never lands in the clone. For branches and merge requests it needs write access, merge requests and reading the check status; the link "Which token branches and pull requests need" in the creation dialog lists the rights, and the "Repository access" dialog of the git panel checks the token and helps issue a new one. A public repository can be read without a token, but then a branch cannot be pushed.

On a server an administrator can set a service access for a repository ("Service access" in `/admin`). Then a new workspace can use **Service access**: branches are pushed with the installation token, commits are signed by you, forks are not available.

The workspace menu:

- **Update base**: fetch the fresh base branch and recount the released versions.
- **Delete**: removes the clone in the Studio (the repository on the hosting stays as is) or only the record of a folder (the folder on disk stays).

## Official packs

The **Official packs** card on the section's main screen opens the packs from the Studio's own repository. You need no repository of your own: edits go to your fork on GitHub and the PR is opened from your account. More: [Propose changes](propose.md#official).

## What next

- [Editing a pack](editing.md): the tree, the editor, "Problems", released versions.
- [Preview and signature places](preview.md): builds on sample data, combinations, signature frames on the PDF.
- [New version](versions.md): the change class, the number, the notes, the release.
- [Propose changes](propose.md): the branch, a PR or an MR, forks, hosting checks.
- [Command line and CI](ci.md): the same checks without the interface, CI for your packs repository.

<!-- T15 (pack and template from scratch): a "New pack" section here, after "Official packs", and an item in "What next". -->
