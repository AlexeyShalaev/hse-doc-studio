---
title: Updating and uninstalling
description: One-click updates with automatic rollback and a clean uninstall; the data folder is never touched.
tags:
  - Updates
  - Docker
---

# Updating and uninstalling

<p class="hds-lede">The Studio updates itself. The data folder is never touched — neither by an update nor by an uninstall.</p>

## Updating

- Settings → **About**: the update button, “What's new”, and switching to any published version, including rollback.
- The updater recreates the container **with all your flags** and **rolls back automatically** if the new version does not come up.
- Auto-update is on by default and never starts during a build; it is disabled in the same place. To fully stop feed requests: `HSE_STUDIO__UPDATE_FEED_URL=off`.

### Manual update { #manual-update }

When the interface is unreachable — or the terminal is simply handier. Same mechanism as the button: a sibling updater container recreates the Studio with all its settings, waits for health and rolls back on failure. The data folder is untouched.

=== "macOS / Linux"

    ```sh
    --8<-- "update-sh.txt"
    ```

=== "Windows (PowerShell)"

    ```powershell
    --8<-- "update-ps1.txt"
    ```

The fallback is a full reinstall (data stays, the wizard recognises the previous install): `docker pull ghcr.io/alexeyshalaev/hse-doc-studio:latest`, `docker rm -f hse-doc-studio`, then the [install command](install.md) again.

## Uninstalling

```sh
docker rm -f hse-doc-studio
docker rmi ghcr.io/alexeyshalaev/hse-doc-studio:latest
# managed neighbours (TeX Live, LanguageTool, ONLYOFFICE, Gotenberg, Ollama)
docker rm -f $(docker ps -aq --filter label=com.hse-studio.managed=true)
```

Images can also be removed beforehand — Settings → **Disk**. The data folder stays: point a fresh install at it and everything comes back.
