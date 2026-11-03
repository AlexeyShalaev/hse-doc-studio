---
title: Local version from the cloud
description: How to install the Studio on your computer and connect it to a cloud Studio to build PDFs locally and work offline.
tags:
  - Installation
  - Sync
---

# Local version from the cloud

<p class="hds-lede">Working in a cloud Studio and want to build on your own machine, offline and without a queue? Install the same Studio on your computer and connect it to the cloud: projects sync on their own and the built PDF goes back to the server.</p>

## Where to find it

In the cloud Studio the "Local version" screen (`/local-studio`) opens from several places:

- the account menu (the circle with your initials, top right), "Local version";
- the empty project list, "Local version" button;
- project settings, "Sync" section, "Clone from the server" block, "Desktop Studio" tab;
- the hint that cloud builds are unavailable right now.

## What you need

- **Docker**: Docker Desktop on macOS and Windows 10/11 (with WSL 2), Docker Engine on Linux.
- **Disk**: about 9 GB for the TeX Live image (downloaded on the first build).
- **Memory**: 2 GB of RAM and 2 cores per build.

## Installation

On the "Local version" screen pick your system and copy the command: your cloud's address is already in it. It looks like this (for `https://studio.example.org`):

=== "macOS / Linux"

    ```sh
    curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | HSE_STUDIO_LANG=en HSE_STUDIO_CONNECT='https://studio.example.org' sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    $env:HSE_STUDIO_LANG='en'; $env:HSE_STUDIO_CONNECT='https://studio.example.org'; irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex
    ```

The script pulls the image, starts the Studio and opens its "Connect to a server" screen in your browser. On first launch the Studio first asks for a projects folder and restarts, keep the tab open.

If port 17240 is taken, the script picks the next one and prints it. Enter that port in "Port on this computer" on the cloud screen so the buttons lead to your Studio. The "Install the same version as the server" checkbox adds `TAG` with the cloud's version to the command.

## Connecting

1. On the cloud screen click "Connect the local Studio" (or click "Connect to a server" on the local Studio's home and paste the cloud address).
2. The local Studio shows the server, its version and its own. If they differ you see a warning: update the local Studio in About or ask the administrator to update the server.
3. Click "Connect to …". The Studio shows a code and opens the confirmation page on the server. Check that the code matches and click "Allow".
4. Done. The access is stored in the local Studio and listed in the cloud under "Settings → Account → Tokens", where you can revoke it.

## Cloud projects in the list

Once connected, the local Studio fetches your projects from the server on its own and shows them on the "Projects" screen next to the local ones. Cloud projects carry a "Cloud" mark:

- **Not open on this computer**: a card with an "Open" button. One click and the Studio downloads the project into the projects folder, shows the progress and opens it. You do not pick a folder or type an address.
- **Open on this computer**: an ordinary project card with the "Cloud" mark. There is no duplicate: projects are matched by the project's identifier on the server.

The list shows only what the server returns to you: other people's projects never appear. The search on the "Projects" screen covers cloud projects too. If something is wrong with the cloud, a line appears above the list: access expired or revoked ("Sign in again" button) or the server is unreachable ("Retry" button). Local projects stay where they are, and working offline does not change.

A project opened from the cloud is already connected to the server: your edits go to the server on their own after a pause, others' edits come in, and the PDF is uploaded to the project after each build (more in [Git sync](../workbench/git-sync.md)).

## Open one particular project

In the cloud project settings ("Sync", "Clone from the server") click "Open in the local Studio". After "Continue" on the connection screen the Studio opens that project: if you already have it, it simply opens, otherwise it is downloaded and then opened. Without a project in the link, "Continue" leads to the project list, where the cloud projects are already shown.

## Folder for cloud projects

Cloud projects are downloaded into the Studio's standard projects folder. Change it under "Settings" → "Repository access" → "Folder for cloud projects": enter a full path on your computer (it must be inside the folders the Studio can access) and save. An empty field brings back the standard folder. Projects already downloaded stay where they are.

A folder of your own for a single project, and projects from other git servers, are still handled by the "Clone from git" wizard on the "Projects" screen.

## A project that is not connected to the cloud

If you created a project in the local Studio instead of opening it from the cloud, it stays on this computer only: neither the edits nor the built PDF reach the server. When the Studio is signed in to a server, the "Build" tab of such a project shows the hint "This project is not connected to the cloud, the PDF will stay on this computer". There is no one-step way to move such a project to the server yet: create the project in the cloud and open it from there.

## Troubleshooting

- **The button opened nothing.** Make sure the Studio is running (`docker ps`) and the port on the cloud screen matches the one the script printed.
- **"Could not connect".** The address must start with `https://`; the cloud must be reachable from this computer.
- **No cloud projects in the list.** Check the line above the list: your access may have expired (click "Sign in again") or the server may be unreachable. An empty list means you have no projects on the server yet.
- **No "Connect" button.** The administrator turned git off on the server: you can work locally, but not link to the cloud.
