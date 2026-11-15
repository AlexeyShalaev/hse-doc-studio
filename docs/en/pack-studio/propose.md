---
title: Propose changes
description: The branch, commits and merge request from Template Studio, forks, hosting checks and contributing to the official packs with your own GitHub account.
tags:
  - Templates
  - Pack authors
---

# Propose changes

<p class="hds-lede">In a git workspace edits go to a working branch and then as a merge request into the base branch: a PR on GitHub, an MR on GitLab. The hosting and the repository maintainers decide on the merge, the Studio only prepares the proposal.</p>

## Branch and versions

Under the workspace title is the git panel: the branch, the edits since the last commit, how many commits the branch is ahead of and behind the base, the open PR and the check status.

- **Save version**: a commit to the working branch in your name. No branch yet: the Studio creates it. The message can stay empty, the Studio writes it from the changed versions (`fix(packs): ...` for patch, `feat(packs): ...` otherwise).
- **Branch**: a new branch named by the Studio, your own name or a switch to an existing branch (only without unsaved edits).
- **Changes**: what differs from the base branch, file by file.
- **Update from** the base branch into the working one. If the main branch edits the same places, the merge is cancelled and the Studio names the files: fix them in your branch, save a version and update again.
- **Start over**: the tree on the fresh base without a branch. Unsaved edits are dropped only with a separate checkbox; the branch and the request on the hosting stay as they are.

## The merge request

**Propose changes**:

1. The Studio checks the changed packs with the same code as `hse-doc-studio pack check --base`: the linter, immutability of released versions, the schemas, the version class. Errors stop the push and show in "Problems"; other people's errors in untouched packs do not get in the way.
2. Unsaved edits are committed and the branch is pushed.
3. A PR or MR to the base branch opens. Write the title and description or leave them to the Studio: it adds a summary to the description (versions, change class, notes, check results). If a request from this branch is already open, the branch is just updated.

If the hosting did not let the API open the request, there is an **Open PR in the browser** link to the compare page.

**No right to write to the repository.** The Studio offers **Push to a fork**: **Create a fork with my token** (GitHub) or **Use my fork** on the same server. The fork is remembered for the workspace.

## Hosting checks { #hosting-checks }

After the push the panel shows the check status of the pushed head: GitHub (check runs and commit statuses) or GitLab (the pipeline, the token needs `read_api`). While checks run, the status refreshes every 30 seconds. **Hosting checks** opens the list with links. If the hosting does not give the status to this token, the link leads to the checks page.

Ready CI for your packs repository: [Command line and CI](ci.md#ci).

## Official packs { #official }

The Studio's own packs live in its repository (`packs/`). Anyone with a GitHub account can propose a fix:

1. The **Official packs** card, the **Start** button. You need your GitHub token: a classic one with the `public_repo` scope (a fork, a branch in the fork and a PR into the public repository). Without a token the dialog gives a link to create one and a field to paste it into: the Studio checks the token, saves it under "Repository access" and selects it right away. The Studio downloads only the packs folder.
2. Edits and a new version as usual.
3. **Propose changes**: the branch goes to your fork and the PR is opened from your account. There is no other way: there is no installation bot for the official packs, this is safer. Commits may touch only the packs folder.
4. Before the first push tick the consent: the contribution is public and licensed under the repository licence. Contribution rules: "Contributing to the official packs" in [CONTRIBUTING.md](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/CONTRIBUTING.md#contributing-to-the-official-packs).

For a PR from a fork of a new contributor GitHub does not run checks until a maintainer approves the run. The Studio shows **Awaiting approval**: this is not an error. The official packs ship with the Studio: after the PR is merged the new version reaches users with the next release.
