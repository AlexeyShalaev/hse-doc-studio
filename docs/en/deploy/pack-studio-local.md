---
title: Template Studio on your computer
description: How a pack author starts the Template Studio with one command on their own computer, without a server or an account, and what to do next.
tags:
  - Deployment
  - Templates
---

# Template Studio on your computer

<p class="hds-lede">The Template Studio edits packs with forms and an editor, builds a preview on test data and sends changes as a pull request. No server of your own is needed: the same Studio image runs on your computer in the "Template Studio only" profile. There is no sign-in or registration, there is one user (you), and projects are hidden.</p>

## What you need

- Docker: Docker Desktop on macOS and Windows, Docker Engine on Linux.
- Disk space for the TeX Live image (several gigabytes). It is downloaded in the background after the first start and is needed for the preview.
- A packs folder (`pack.yaml` in each pack folder, packs at the root of the folder or in a `packs/` subfolder). A git repository of your own needs no folder, you add it in the interface.

## Start

Put the profile file into a folder of its own and say in `.env` where the packs are:

```sh
mkdir -p ~/hse-pack-studio && cd ~/hse-pack-studio
curl -fsSLO https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/pack-studio/docker-compose.yml
echo "PACKS_DIR=$HOME/my-packs" > .env
docker compose up -d
```

Open <http://localhost:17260>. The Template Studio opens right away, and the packs folder is already in the list of workspaces.

- Without `PACKS_DIR` the folder the command runs in is opened.
- Data (repository clones, git access, preview builds) lives in `~/.hse-pack-studio`; set `DATA_DIR` for another folder.
- The other variables (port, TeX image, fonts) are described in [`.env.example`](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/deploy/pack-studio/.env.example).

!!! note "Linux"
    The Studio writes to the packs folder and to `DATA_DIR` as its own user. Run it with your uid and give it the Docker socket by adding to `.env`:

    ```sh
    echo "HSE_UID=$(id -u)" >> .env
    echo "HSE_GID=$(id -g)" >> .env
    echo "DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)" >> .env
    ```

!!! note "macOS"
    Docker Desktop does not share the system fonts (Times New Roman, Arial) with containers: without them the preview uses free substitutes. Copy the fonts into a folder under your home and set it in `HOST_FONTS_DIR` (an example is in `.env.example`), or upload them in **Settings, "Fonts"**.

!!! note "Windows"
    Create `.env` with an absolute path, for example `PACKS_DIR=C:/Users/me/my-packs`, and run `docker compose up -d` in PowerShell.

## What next

1. **Packs folder.** Open the workspace, pick a version file (`version.yaml`) and press **Build** in the preview tab. The first build waits for the TeX image.
2. **Your own packs repository.** Add a token in **Settings, "Git access"**, then **New workspace**, git tab: the repository address and the token. Edits go to a branch, and **Propose changes** opens a PR (GitHub) or an MR (GitLab).
3. **Official packs.** The **Official packs** card, **Start** button: the packs of the Studio repository; changes go through your fork with your GitHub token. The rules are in "Contributing to the official packs" of [CONTRIBUTING.md](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/CONTRIBUTING.md#contributing-to-the-official-packs).
4. **How a pack is built.** Files, versions and what counts as patch, minor and major: [Packs and templates](../reference/pack.md).
5. **Working in Template Studio.** Editing, previews, signature places, a new version and merge requests: [Template Studio](../pack-studio/index.md).

## Update and stop

```sh
docker compose pull && docker compose up -d   # a new Studio version
docker compose down                           # stop, the data stays
```

## For Studio developers

In a checkout of the repository, `make pack-studio` starts the same from sources: api and Vite at <http://localhost:3001/pack-studio>, a workspace over `packs/` of the checkout, data in `.pack-studio/`. The preview build needs a local Docker.
