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
