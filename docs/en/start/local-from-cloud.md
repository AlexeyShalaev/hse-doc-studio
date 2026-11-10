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

A project opened from the cloud is already connected to the server: your edits go to the server on their own after a pause, others' edits come in, and the PDF is uploaded to the project after each build (more in [Git sync](https://alexeyshalaev.github.io/hse-doc-studio/workbench/git-sync/), in Russian).

## Open one particular project

In the cloud project settings ("Sync", "Clone from the server") click "Open in the local Studio". After "Continue" on the connection screen the Studio opens that project: if you already have it, it simply opens, otherwise it is downloaded and then opened. Without a project in the link, "Continue" leads to the project list, where the cloud projects are already shown.

## Folder for cloud projects

Cloud projects are downloaded into the Studio's standard projects folder. Change it under "Settings" → "Repository access" → "Folder for cloud projects": enter a full path on your computer (it must be inside the folders the Studio can access) and save. An empty field brings back the standard folder. Projects already downloaded stay where they are.

A folder of your own for a single project, and projects from other git servers, are still handled by the "Clone from git" wizard on the "Projects" screen.

## A project that is not connected to the cloud

If you created a project in the local Studio instead of opening it from the cloud, it stays on this computer only: neither the edits nor the built PDF reach the server. When the Studio is signed in to a server, the "Build" tab of such a project shows the hint "This project is not connected to the cloud, the PDF will stay on this computer". There is no one-step way to move such a project to the server yet: create the project in the cloud and open it from there.

## What your Studio is doing: the badge in a project

In the project header, before the sync button, there is a badge: a coloured dot and a label. Click it for details. The same data is visible from both sides.

**In the cloud** the badge names your local Studios: "Studio online: Alex's MacBook" or "Studio offline". The panel shows for every Studio:

- the device name (set in the local Studio), the version, online or "was online 5 minutes ago", and what the Studio is doing now (idle, syncing, building);
- the sync of this project: the last sync, how many changes are ahead and behind, whether auto-sync is on, the last PDF upload and when;
- the personal runner of this Studio: online or not, tags, busy or free;
- AI through this Studio: whether Ollama is visible, which models, and if the cloud cannot use them, the reason and what to do.

Other project members see only "Working locally: Boris", and only while Boris's Studio is online. They do not see the name of his computer, the version, the runner or the models, and an instance administrator sees exactly as much as any member. The list of all your Studios with a "Forget device" button is in "Settings, My runners, My Studios".

**In the local Studio** the same badge shows the link to the cloud: "Cloud online", "Cloud cannot see the Studio", "No connection to the server", "Server sign-in expired" or "revoked". The panel shows the server and who you are signed in as, whether the cloud sees this Studio and when the last signal was sent, the runner and the models opened to the cloud with their state on the cloud side, the last sync and PDF upload, and which other project members are working locally right now.

**People in the project.** Next to the badge you see avatars of everyone who is in this project right now, in the cloud or in their own Studio, with where they are (“is editing “Proposal””, “is working locally”). The local Studio shows the same list when it is signed in to the server and you may read sources; without a server there are no avatars. More: [Who is in the project now](../workbench/people-online.md).

### Computer name

The cloud shows the Studio under the computer's name. If it is not named (inside a container the host name is a random string), it is "Local Studio". Change it in "Settings, Cloud builds, Link with the cloud": an empty field returns the default name.

### What goes to the server

Once a minute the Studio sends the server a short signal: the device name, the version, what it is doing, the runner state and the model names, and for every cloud project a sync code and the numbers ahead and behind. There are no disk paths, document contents, model addresses or keys in the signal. It goes over the same sign-in as the sync, without a permanent connection; if you revoke the sign-in on the site, the Studio stops being "online" after three minutes. More: [What goes over the network](../reference/privacy.md).

## AI through your Studio

In the local Studio open "Settings, Cloud builds, Models for the cloud" and click "Open for the cloud" next to the model (for example, Ollama on this computer). This only announces the model to the server. For the cloud to start using it, **add a "Through my runner" provider in the cloud once**: "Settings, AI providers, Add", pick your Studio and the model. It is simpler to click "Add in the cloud" in the Studio panel or in the banner above the provider list, which appears when a model is opened but there is no provider. After that the model shows up in the chat model picker.

If the model does not work, the Studio panel names the reason:

| State | What to do |
|---|---|
| The provider is not added in the cloud | click "Add in the cloud" |
| Nothing is opened to the cloud | "Open for the cloud" in the local Studio |
| The Studio is not connected as a runner | "Cloud builds", "Connect" |
| The Studio or the runner is offline | start the local Studio |
| The runner is paused, revoked or personal runners are off | unpause, reconnect or ask the administrator |
| The Studio is online but the model does not answer | start Ollama |
| No models | pull a model |

Two common causes of errors in the model itself. Ollama accepts at most 4096 tokens by default, while an agent request in a project needs about 5000: the chat says the request "does not fit the model window", so raise the context (`num_ctx`, for example 16384) or take a model with a larger window. If the Studio is online but Ollama is stopped, the chat says the model on that computer does not answer.

## Which documents are built through your Studio

Connected as a personal runner, your Studio takes two kinds of jobs from the cloud, and each needs its own setup.

| Document | What you need on your computer |
|---|---|
| LaTeX (PDF) | Docker and the TeX Live image (the same one local builds use) |
| Presentations and office files (pptx, docx, odt, xlsx and others) | Docker and the Gotenberg image (`docker pull gotenberg/gotenberg:8`) |
| Archives and signature checks | nothing, always available |

Nothing needs switching on for office files: the Studio starts its own Gotenberg conversion service when such a job arrives and stops it after idle time, as it does for local builds. While Docker is not running or the Gotenberg image is not downloaded, the Studio does not tell the cloud it can build office documents, and the cloud keeps showing the "No connected runner for office documents" banner. Once Docker is up and the image is present, the Studio reconnects on its own (checked once a minute) and the banner goes away. If Docker is stopped, the capability is withdrawn the same way, so the cloud does not send a job nobody can run. The Gotenberg image comes from the Studio office-service settings (gotenberg/gotenberg:8 by default); the image named by the cloud is not used.

## Builds in the cloud and on your side

For each document, in the list and in the "Build" panel, you can see where and when it was last built (cloud, this Studio, another Studio), from which version of the project and whether the PDF is fresh: "matches the cloud", "outdated: the project changed", "in the cloud 5 min, you have none". "Fresh" means the PDF was built from the current version of the project; a PDF with no recorded version is never called fresh.

If a document is built in the cloud and you do not have it, click "Get the build" in the local Studio: the ready PDF is downloaded over the same sign-in and the document opens without a rebuild. The Studio does not download what you already have (compared by the file fingerprint), does not replace a newer local build (use "Replace anyway") and does not download a file over the size limit. A document that is not produced as a PDF (a pptx presentation, for example) cannot be fetched this way: the cloud keeps only PDFs, and the file itself arrives with the sources on sync, so such a document is left out of "Get cloud builds" and its note says to build it here. When auto-sync is on for the project, the Studio gets the cloud PDF by itself after a sync, but only the build of the version you have, and not on a mobile network or in data-saver mode. The other direction has long worked: after a build the local PDF goes to the server and shows in the project overview.

## Troubleshooting

- **The button opened nothing.** Make sure the Studio is running (`docker ps`) and the port on the cloud screen matches the one the script printed.
- **"Could not connect".** The address must start with `https://`; the cloud must be reachable from this computer.
- **No cloud projects in the list.** Check the line above the list: your access may have expired (click "Sign in again") or the server may be unreachable. An empty list means you have no projects on the server yet.
- **No "Connect" button.** The administrator turned git off on the server: you can work locally, but not link to the cloud.
