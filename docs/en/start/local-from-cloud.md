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

## Open a project locally

In the cloud project settings ("Sync", "Clone from the server") click "Open in the local Studio". If you already have the project, it opens. Otherwise the clone wizard opens with the address and access filled in: pick a folder and click "Clone". From then on the Studio pushes your edits, pulls others' and uploads the PDF after each build.

## Troubleshooting

- **The button opened nothing.** Make sure the Studio is running (`docker ps`) and the port on the cloud screen matches the one the script printed.
- **"Could not connect".** The address must start with `https://`; the cloud must be reachable from this computer.
- **No "Connect" button.** The administrator turned git off on the server: you can work locally, but not link to the cloud.
