---
title: Server auto-update
description: New release checks, automatic install in a maintenance window with a backup, image verification and automatic rollback; Helm.
tags:
  - Deployment
  - Operations
---

# Server auto-update

<p class="hds-lede">The Studio learns about new releases by itself and, if you allow it, installs them at night: it takes a database snapshot, verifies the image, applies migrations, restarts the services and goes back to the previous version by itself if the new one does not come up. Everything is configured in the admin, section "Updates".</p>

Design and decisions: `docs/design/auto-update.md` in the repository.

## What to enable

Release checks and notifications work right away. Installing is done by a separate `updater` service that needs access to docker. Enabling it for compose:

```bash
# in .env: a shared secret of the api and the updater
UPDATER_TOKEN=$(openssl rand -hex 32)
# .env must be writable by the app user (uid 10001) so the updater can advance TAG
chmod o+w .env
docker compose --profile updater up -d
```

A minute later the Updates section shows "Updater: running". Without the token the service does not start and the Studio only reports versions.

!!! danger "The docker socket is root"
    `updater` has `/var/run/docker.sock`, like the runner. It publishes no ports and takes work only from the api by a shared secret, but a compromised host or secret means root. The service stays off until you enable the profile. If that is unacceptable, keep the "Notify" mode and update by hand.

## Policy

| Mode | What it does |
|---|---|
| Off | releases are not checked |
| Notify (default) | asks the stable channel every 6 hours and notifies admins; you install with the button |
| Install automatically | installs by itself in the maintenance window |

For automatic installs you set: the largest step without a human (patches only, or patches and minors; a new major version is always notify-only), the window days and time in UTC (default every day from 02:00 for 3 hours), whether a full backup is taken first, and image verification. A version that already rolled back is not retried by itself: we wait for the next release.

## How an update goes

1. If the Backups section has a destination, a full backup runs and the update waits for its success. The backup failed: the update is cancelled, nothing is touched.
2. The updater takes a database snapshot and pins the previous image.
3. It pulls the new image and verifies it: the digest equals the one published with the release (`image-digest.json`); with "Digest and signature" the cosign signature too.
4. It stops the runner and the api (the Studio is unavailable from here, usually 1-3 minutes), applies migrations and starts the services on the new image.
5. It waits for health: containers run, do not restart, `/health/ready` answers 200 for twenty seconds in a row.

Something went wrong in steps 4-5: the previous images come back automatically. If migrations already changed the database schema, the database is first restored from the snapshot (the old image does not start on a newer schema); no data is lost because the api was stopped. Administrators get a notification and the history shows the run log.

## Manual rollback

The "Roll back to X" button is available while the version of the last successful update is installed. If the update changed the database schema, the rollback restores the snapshot taken before it: **everything written after the update is lost**, so an explicit confirmation is required. Without a schema change the rollback only brings back the images.

## Helm

Kubernetes has no updater (`HSE_STUDIO__SERVER_UPDATE__EXECUTOR=none`): the Studio checks releases and notifies you, the page shows a ready command, and Helm rolls back by itself:

```bash
helm upgrade hse-doc-studio deploy/helm/hse-doc-studio --reuse-values --set image.tag=0.4.0 --atomic --wait
```

Migrations run as a separate Job before the upgrade. To stop notifications set `api.extraEnv.HSE_STUDIO__SERVER_UPDATE__ENABLED=false`. You can verify the image beforehand: `cosign verify` with the `publish.yml` workflow identity.

## When something is wrong

| Symptom | What to do |
|---|---|
| "The updater does not answer" | `docker compose --profile updater ps`, `docker compose logs updater`; the token in `.env` and in the api must match |
| "This release publishes no digest" | the release predates auto-update; install it by hand or pick "None" verification |
| Status "Needs hands" | the rollback failed; the run log names the snapshot (`snapshots/...` in the `updater-data` volume), then `docker compose up -d` |
| Update cancelled `unsupported_container_options` | a container has options the updater cannot carry over; update by hand |
| TAG in `.env` does not change | the file is not writable by the app user: `chmod o+w .env` |

Metrics for alerts: `hse_update_available`, `hse_update_updater_up`, `hse_update_last_run_success`, `hse_update_runs_total{result}`. Process settings: `HSE_STUDIO__SERVER_UPDATE__*` in the [reference](env-reference.md).
