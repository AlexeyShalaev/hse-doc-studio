---
title: Pack catalogs
description: How a server administrator connects third-party template packs from git or an archive so they appear in the project wizard without rebuilding the image or restarting.
tags:
  - Deployment
  - Templates
---

# Pack catalogs

<p class="hds-lede">The project wizard shows the packs built into the Studio image. Your own packs (another programme, department or university) can live in your own git repository and be edited in the Pack Studio. The Template sources section of the admin panel connects such packs to this instance: they appear in the project wizard without rebuilding the image and without a restart.</p>

## Sources

| Source | What to give | When |
|---|---|---|
| Git | repository address, packs folder (`packs` by default), tag, branch or sha (empty: the default branch), access | the server can reach the repository |
| Archive | a .zip or .tar.gz file with the packs folder | closed network without access to the hosting |

Access to a private repository: your personal access from Git access (a token for that host) or the repository service access from the Pack Studio section. A public repository needs no access.

Locally (the Studio on your own computer) there is no admin panel: in the Pack Studio a workspace over a folder has the **Connect to this Studio's catalog** button, the rest works the same way.

## Check and apply

1. **Add a source.** The check opens right after adding it.
2. **Check.** The Studio downloads the chosen revision, reads the packs with its own loader in a separate process with time and memory limits, runs the pack linter and the release immutability check and shows a plan:

    | Mark | Meaning |
    |---|---|
    | will appear | a new released version, after Apply it is in the wizard |
    | already there | this version is already in the catalog with the same content |
    | changed in the source | a version with this number is already in the catalog with other content; cannot apply |
    | not for this Studio | needs a newer Studio (`min_studio`) or an unknown manifest format; appears after updating the Studio |
    | with errors | the linter found errors or the version folder changed after release |
    | not released | the version is not in the source `releases.yaml`; only released versions enter the catalog |

3. **Apply.** Exactly the checked revision is applied. If the source changed after the check, the Studio asks to check again. The versions go to the store and the catalog switches at once in every server process.

Applying is refused when a pack with the same id is built into the Studio (the **Replace built-in** checkbox is needed), when another source already provides the pack, when a version changed in the source, or when a new version has errors.

## Immutability

- A version used by projects is never removed or replaced. The store only grows: each version lives under its digest in `data_dir/packs-store`.
- The same number with other content is refused as "changed in the source". A fix in a pack is a new version.
- **Turn off** hides the source packs from the project wizard, **Remove** removes the source itself. The versions stay: existing projects open and build as before.
- A pack with the id of a built-in pack is connected only with **Replace built-in**. Built-in versions stay for projects, the wizard offers the source versions.

## Tracking

The **Track daily** checkbox of a git source: once a day the Studio checks the revision and applies new released versions when the plan is clean. If something blocks, nothing is applied and the error shows on the source and in its history. The check runs on behalf of the administrator who connected the source (their git access).

## Builds on runners

Runners (the built-in one, cluster runners and personal runners) need no packs: when a project is created the template files are copied into the project folder, and before each build the server refreshes the dynamic files (`meta.tex`) and hands the whole project to the runner. So a project on a connected pack builds wherever a project on a built-in pack builds.

## History and audit

Each source has a **History**: adding, edits, checks, applies, turning off, tracking. The same actions go to the instance audit log (`pack_catalog.source_add`, `pack_catalog.source_update`, `pack_catalog.check`, `pack_catalog.apply`, `pack_catalog.source_enable`, `pack_catalog.source_disable`, `pack_catalog.source_remove`, `pack_catalog.track`).

## Limits and security

| Variable | Default | Limits |
|---|---|---|
| `HSE_STUDIO__PACK_CATALOG__MAX_ARCHIVE_BYTES` | 100 MiB | archive size and the amount fetched from git |
| `HSE_STUDIO__PACK_CATALOG__MAX_FILES` | 20 000 | files in a revision |
| `HSE_STUDIO__PACK_CATALOG__MAX_BYTES` | 512 MiB | total size of the revision files |
| `HSE_STUDIO__PACK_CATALOG__INSPECT_TIMEOUT_S` | 120 | time to read a revision |

An archive with symbolic links, absolute paths or paths leaving its folder is refused as a whole. Git is fetched without hooks, submodules and links, only the packs folder. Pack templates run only in the sandbox.
