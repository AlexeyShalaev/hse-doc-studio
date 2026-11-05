---
title: Troubleshooting
description: Diagnosis by symptom — Docker not responding, permission denied on the socket, taken port, endless setup.
tags:
  - Troubleshooting
  - Docker
---

# Troubleshooting

<p class="hds-lede">Symptom → what to do. If yours is missing — <a href="https://github.com/AlexeyShalaev/hse-doc-studio/issues">open an issue</a>.</p>

- **“Docker is not responding”** — start Docker Desktop (Windows/macOS) or `sudo systemctl start docker` (Linux); for Colima — `colima start` plus `DOCKER_SOCK="$HOME/.colima/default/docker.sock"`.
- **Runs, but builds nothing** (“permission denied” on the socket) — `--group-add 0` is enough for Docker Desktop; on Linux recreate the container with `--group-add "$(stat -c '%g' /var/run/docker.sock)"`. Settings → Compiler shows the ready-made line.
- **Port 17240 is taken** — the script tries 17241…17250 by itself; manually, change the left side of `-p`: `-p 18000:8000`.
- **Setup wizard “waits forever”, setup rolls back** — the container was started without `-e HSE_STUDIO__SERVER__PORT=8000` (the HEALTHCHECK watches 8000): recreate it with the full command from [Installation](install.md). Or the socket permissions are missing — run the “Run manually” command the wizard shows.
- **Git Bash mangles paths** (`/var/run/docker.sock` → `C:\Program Files\Git\…`) — prefix with `MSYS_NO_PATHCONV=1` or use PowerShell.
- **Compose does not see the projects folder** — `DATA_DIR` in `.env` must be an absolute path, otherwise Docker treats it as a volume name.
- **The first build “hangs”** — the TeX Live image is downloading (≈ 9 GB), progress is on the Build tab; it happens once.
- **Low disk space** — Settings → **Disk**: build-cache cleanup and image removal with an explicit list.
- **A build says “failed” and the reason is not visible** — open the document's Build tab: it has the code and a “what to do” text, and the document list shows the reason under the name. Code table: [“Build and log”](../workbench/compile.md#when-a-build-fails).
- **“A new version of Studio is out” or “Failed to fetch dynamically imported module”** — the tab was opened on an old version and the server has been updated since: the files it pointed to are gone. Studio reloads the page once by itself; if the editor holds unsaved text it does not, and shows a “Refresh” notice instead. Press the button (your edits are saved first) or reload the page (`Ctrl+R`, pull down on a phone). If the message comes back after a reload, clear the site cache; for administrators: a proxy or CDN must not cache `index.html` and `/version.json`, nor answer a missing `/assets/*` with another page.
