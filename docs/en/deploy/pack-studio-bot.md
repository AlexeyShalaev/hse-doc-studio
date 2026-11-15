---
title: Official packs without a GitHub account
description: How a server administrator sets up a service account (bot) through which people without their own GitHub account propose changes to the official Studio packs.
tags:
  - Deployment
  - Templates
---

# Official packs without a GitHub account

<p class="hds-lede">The Pack Studio has an Official packs card: the packs of the Studio repository itself, edited with the mouse and proposed through a PR. A person with their own GitHub token sends changes through their own fork. For people without a GitHub account the administrator can provide an instance service account (bot): the branch goes to the bot's fork, the PR is opened from the fork, and the PR description names the author from their Studio profile.</p>

## What the bot does and does not do

- Pushes the branch **only to its own fork**. The Studio never pushes into the official repository, even if the bot could.
- Opens the PR from the fork into the official repository. The commit author is the person: profile name, a Studio noreply address, the real email stays private.
- Works only for people with the Pack author right (granted in the Pack Studio section of the admin area).
- Refuses a branch that changes anything outside the packs folder.
- Allows at most the set number of proposals per person per 24 hours (5 by default).
- Every use of the token and every proposal goes to the audit log (`pack_studio.service_access_use`, `pack_studio.proposed`).

## Which token

You need a **classic GitHub personal access token with the `public_repo` scope**.

A fine-grained token does not work: GitHub does not let it contribute to public repositories where the token owner is not a member, so it cannot open a PR from the fork into the official repository. The `repo` and `workflow` scopes are not needed: packs do not touch `.github/workflows`, and the repository is public.

## Step by step

1. **Create a separate GitHub account for the bot**, for example `hse-doc-studio-bot` for your instance. The administrator's personal account does not fit: other people's PRs would be opened in its name.
2. Turn on two-factor authentication for the bot account and keep the recovery codes in your secrets store.
3. In the bot account open **Settings, Developer settings, Personal access tokens, Tokens (classic)** and click **Generate new token (classic)**.
    - Note: for example `HSE Doc Studio, official packs`.
    - Expiration: per your policy (for example 90 days); before it expires create a new one and replace the access.
    - Scopes: check only **`public_repo`**.
4. Copy the token (`ghp_...`). GitHub shows it once.
5. In the Studio open **Admin, Pack Studio, Official packs** and click **Add a bot**. The official repository address is filled in and **Fork only (bot)** is checked. Paste the token and save. The token is encrypted and never shown again.
6. In **Service access** click **Check** next to the bot. The check shows the token account and its scopes and creates the fork in the bot account (or finds the existing one). If it names a problem, fix it:

    | Problem | What to do |
    |---|---|
    | fine-grained token | create a classic token (step 3) |
    | no `public_repo` scope | create the token again with this scope |
    | GitHub did not accept the token | it is revoked or expired: create a new one |
    | the fork could not be created | check the scope and that the bot has no repository with the same name |
    | the bot has write access | harmless, but better remove the bot from the official repository collaborators |

7. Grant the Pack author right to people or organization groups. The Official packs card in the Pack Studio then offers **Without your own GitHub account**.

## Switch and limit

In the **Official packs** section of the admin area:

- **Contributing without a GitHub account** turns the bot off entirely: proposals through it are refused, proposing with your own token keeps working.
- **Proposals per person per day** protects against spam in the bot's name. It counts the audit log over the last 24 hours. The default comes from `HSE_STUDIO__PACK_STUDIO__OFFICIAL_BOT_DAILY_LIMIT`.

## Your own official repository

Environment variables set the official repository:

| Variable | Default |
|---|---|
| `HSE_STUDIO__PACK_STUDIO__OFFICIAL_REPO_URL` | `https://github.com/AlexeyShalaev/hse-doc-studio` |
| `HSE_STUDIO__PACK_STUDIO__OFFICIAL_PACKS_PATH` | `packs` |
| `HSE_STUDIO__PACK_STUDIO__OFFICIAL_BASE_BRANCH` | `master` |
| `HSE_STUDIO__PACK_STUDIO__OFFICIAL_LICENSE` | `Apache-2.0` |

A fork of the Studio points to its own repository; an empty `OFFICIAL_REPO_URL` hides the Official packs card.

## What people see

- Before the first proposal the Studio asks to agree that the contribution is public and goes under the repository license, with a link to the contributing rules.
- For a PR from a fork of a new contributor GitHub does not run the checks until a repository maintainer approves the run. The Studio says so in words, "awaiting approval", not an endless "pending".
- Official packs ship with the Studio: after the PR is merged, the Studio says the new version reaches users with the next release.
