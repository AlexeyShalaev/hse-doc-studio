---
title: Installation
description: A one-line script, a manual docker run with the key flags explained, and Docker Compose with overlays.
tags:
  - Install
  - Docker
---

# Installation

<p class="hds-lede">Three ways, in ascending order of control. The script suits nearly everyone. After installation the app greets you with the first-run wizard.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/setup</span></div>
    <img src="../assets/shots/setup.en.light.png#only-light" alt="First-run wizard">
    <img src="../assets/shots/setup.en.dark.png#only-dark" alt="First-run wizard">
  </div>
  <figcaption>the first-run wizard: one folder for your works — nothing else to configure</figcaption>
</figure>

## Way 1 · One-line script

=== "macOS / Linux"

    ```sh
    --8<-- "install-sh.txt"
    ```

=== "Windows (PowerShell)"

    ```powershell
    --8<-- "install-ps1.txt"
    ```

The script asks nothing: it checks that Docker responds, pulls the image, starts the `hse-doc-studio` container and opens the browser. Default port is 17240 (if taken, it tries 17241…17250). Re-running is safe: an existing container is not recreated, your data folder is never lost.

Environment variables: `PORT`, `TAG`, `HSE_STUDIO_IMAGE`, `HSE_STUDIO_NAME`, `HSE_STUDIO_LANG` (script message language: `ru` for Russian, English without the flag), and in the sh version `DOCKER_SOCK` for Colima and Rancher Desktop:

```sh
DOCKER_SOCK="$HOME/.colima/default/docker.sock" curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | sh
```

## Way 2 · Manually, no scripts

One line, identical for sh, cmd and PowerShell:

```
--8<-- "install-docker-run.txt"
```

Then open <http://localhost:17240> and [create your first project](first-project.md). The data directory is deliberately not set here: the setup wizard asks for one folder and recreates the container with the right `-v` itself.

The flags:

| Flag | Why |
|---|---|
| `-e HSE_STUDIO__SERVER__PORT=8000` | The image HEALTHCHECK watches port 8000 — without it a recreated container is forever considered “not up”. |
| `-v /var/run/docker.sock:…` | Via the socket the Studio runs TeX Live, recreates itself after the wizard and updates with one click. |
| `--group-add 0` | Access to the Docker socket: `0` is enough for Docker Desktop; **on Linux** use the real gid — `--group-add "$(stat -c '%g' /var/run/docker.sock)"`. |
| `--add-host=host.docker.internal:host-gateway` | Reach services running on the host — e.g. native Ollama. |
| `-p 17240:8000` | The port in your browser; want another one — change the left side. |

!!! warning "Git Bash on Windows"
    Git Bash rewrites `/var/run/docker.sock` into a Windows path — prefix the command with `MSYS_NO_PATHCONV=1` or use PowerShell.

## Way 3 · Docker Compose

```sh
--8<-- "install-compose.txt"
```

Then open <http://localhost:17240>. `.env` sets `PORT`, `TAG`, `DATA_DIR` (**an absolute path is mandatory**), `DOCKER_GID`, `UPDATE_FEED_URL`. With `DATA_DIR` set, the setup wizard is skipped — and it deliberately refuses to “fix” a Compose install.

Three overlays you can stack:

```sh
# build the image from source instead of GHCR (and mount packs/ for live template editing)
docker compose -f docker-compose.yml -f compose.build.yml up -d --build

# keep projects in your own host folder (enables path translation)
PROJECTS_HOST_PATH=D:/study docker compose -f docker-compose.yml -f compose.projects.yml up -d

# give the Studio your OS fonts (Settings → Fonts → System)
SYSTEM_FONTS_PATH=C:/Windows/Fonts docker compose -f docker-compose.yml -f compose.system-fonts.yml up -d
```

## What's next

Open <http://localhost:17240> and [create your first project](first-project.md).
