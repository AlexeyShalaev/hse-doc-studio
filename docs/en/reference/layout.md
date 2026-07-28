---
title: On-disk layout
description: What lives in the data folder and the project folder, what the Studio manages, and what is enough to back up.
tags:
  - Reference
  - Files
---

# On-disk layout

<p class="hds-lede">The Studio has no database — all state is files in two places: the data folder you chose at first run, and the project folders. Back these up and you have backed up everything.</p>

## The data folder

Chosen in the [setup wizard on first run](../start/first-project.md) (`/data` inside the container):

```
<data folder>/
├─ config.json                # app settings (theme, engine, compiler…)
├─ projects.json              # the project index (paths, pinned, archived)
├─ ai_providers.json          # AI providers (keys live here, locally)
├─ agent_personas.json        # your agent personas
├─ update-check.json          # the cached last update check
├─ office-editor-jwt.secret   # the ONLYOFFICE editor secret
└─ fonts/                     # managed fonts — mounted into TeX Live
```

Settings and providers move between machines via Settings → **Import / Export** (optionally as an encrypted file).

## The project folder

Each project is a self-contained folder; the path is shown in Project settings:

```
<project folder>/
├─ technical_specification/   # document folders — plain .tex and resources
├─ thesis/
├─ presentation/
├─ …
├─ .build/<document>/         # build outputs: PDF, .log, .synctex.gz
├─ .hse-studio/               # the Studio's own space:
│  ├─ git/                    #   change history (a separate git, not yours)
│  ├─ history.json            #   the document journal
│  ├─ forms/                  #   form answers
│  ├─ compiles/  chats/       #   build and agent-chat metadata
│  ├─ submissions/            #   packaged submissions
│  └─ pdf-archive/            #   PDFs of past builds (for “Compare”)
└─ project.json               # the project passport: pack, version, authors, meta
```

## House rules

- **Document files are yours.** Edit them with anything; the Studio notices external edits and offers a diff.
- **`.hse-studio/` is the Studio's territory.** Best left alone; you can exclude it from your own VCS.
- **`.build/` regenerates** — safe to clean and to gitignore.
- **Your own git on top is welcome.** The Studio's history lives isolated in `.hse-studio/git/` and does not conflict with your repository.

## What to back up

The minimum: **the data folder + the project folders**. After a reinstall (or on a new machine) point the wizard at the same data folder — and continue where you left off. Docker images need no backup — they re-download.
