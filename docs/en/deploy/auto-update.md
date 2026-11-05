---
title: Server auto-update
description: New release checks, automatic install in a maintenance window with a backup, image verification and automatic rollback; compose and Kubernetes.
tags:
  - Deployment
  - Operations
---

# Server auto-update

<p class="hds-lede">The Studio learns about new releases by itself and, if you allow it, installs them at night: it takes a database snapshot, verifies the image, applies migrations, restarts the services and goes back to the previous version by itself if the new one does not come up. Everything is configured in the admin, section "Updates".</p>

Design and decisions: `docs/design/auto-update.md` in the repository.

## What to enable

Release checks and notifications work right away. Installing is done by a separate `updater` service: in compose it needs access to docker, in Kubernetes rights on the api Deployment (see "Kubernetes" below). Enabling it for compose:

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

## How an update goes (compose)

1. If the Backups section has a destination, a full backup runs and the update waits for its success. The backup failed: the update is cancelled, nothing is touched.
2. The updater takes a database snapshot and pins the previous image.
3. It pulls the new image and verifies it: the digest equals the one published with the release (`image-digest.json`); with "Digest and signature" the cosign signature too.
4. It stops the runner and the api (the Studio is unavailable from here, usually 1-3 minutes), applies migrations and starts the services on the new image.
5. It waits for health: containers run, do not restart, `/health/ready` answers 200 for twenty seconds in a row.

Something went wrong in steps 4-5: the previous images come back automatically. If migrations already changed the database schema, the database is first restored from the snapshot (the old image does not start on a newer schema); no data is lost because the api was stopped. Administrators get a notification and the history shows the run log.

## Manual rollback

The "Roll back to X" button is available while the version of the last successful update is installed. If the update changed the database schema, the rollback restores the snapshot taken before it: **everything written after the update is lost**, so an explicit confirmation is required. Without a schema change the rollback only brings back the images.

## Kubernetes

There are two ways, pick one.

### Buttons in the admin: the `kubernetes` executor

It is turned on by a chart flag (off by default):

```bash
helm upgrade hse-doc-studio deploy/helm/hse-doc-studio --reset-then-reuse-values \
  --set updater.enabled=true --set updater.token=$(openssl rand -hex 32)
```

You can keep the token out of the values and add an `updater-token` key to `secrets.existingSecret`. The chart adds an `updater` pod and switches the api to the `kubernetes` executor (`HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes`). A minute later the Updates section shows "Updater: running", and "Update now" and "Roll back" work.

What it does: verifies the image (the release digest is written into the Deployment, with "Digest and signature" the cosign signature is checked by a separate Job), runs a `db current` Job on the new image, stops the api (`replicas: 0`), applies the migrations in a `db upgrade` Job, changes the image of the `api` Deployment and waits for health. It relies on the Deployment and the Job, not on the Helm release record, so it works for installs without Helm too (Kustomize, hand-written manifests). The Studio is unavailable from the api stop until the new version is ready, usually 1-3 minutes plus the migration time.

The updater's rights are limited to its namespace: `get` and `patch` on one api Deployment by name, Jobs (create, read, delete), reading pods and their logs. It has no secrets, no other namespaces and no `ClusterRole`. The pod and the Jobs pass Pod Security `restricted`.

!!! warning "There is no database snapshot in Kubernetes"
    An image older than the schema does not start, so the image can be rolled back only while the migrations did not change anything. The protection is:

    - if Backups has a destination, a full backup runs before the update and the update waits for its success;
    - otherwise a manual update asks you to confirm the risk ("I understand: there will be no full backup and the database cannot be rolled back") and auto-install does not start: administrators get a notification. If "no backups" is [accepted on purpose](diagnostics.md#accepting-a-warning-on-purpose) in self-diagnostics, a manual update does not ask for the confirmation and shows one line, "Backups are off on purpose, reason: ..."; auto-install still does not start;
    - the new version did not come up and the migrations did not change the schema: the image and replicas come back by themselves, the result is "Rolled back";
    - the new version did not come up and the **migrations changed the schema**: the image is not rolled back (the old one does not start on the new schema), the status is "Needs hands". The run log (the "Log" button) says what the Deployment holds, how to diagnose, and two ways: remove the cause and let the pod restart, or restore the database from the backup and put the previous image back with `kubectl set image` and `kubectl scale` (names already filled in);
    - the "Roll back" button is available while the last update did not change the schema; otherwise the page explains why it is missing.

After updating from the admin, pin the version in your values (or in the GitOps repository): the next `helm upgrade` without `--set image.tag=<version>` brings back the image from the values. The job runner (if enabled) and the updater itself are updated with `helm upgrade` together with the chart: the admin changes only the api Deployment, and an incompatible runner version is rejected at registration.

### Operator command: Helm and GitOps

If the executor is off (`HSE_STUDIO__SERVER_UPDATE__EXECUTOR=none`, the default), the Studio checks releases and notifies you, the page shows a ready command, and Helm rolls back by itself:

```bash
helm upgrade hse-doc-studio deploy/helm/hse-doc-studio --reuse-values --set image.tag=0.4.0 --atomic --wait
```

Migrations run as a separate Job before the upgrade. To stop notifications set `api.extraEnv.HSE_STUDIO__SERVER_UPDATE__ENABLED=false`. You can verify the image beforehand: `cosign verify` with the `publish.yml` workflow identity.

## When something is wrong

| Symptom | What to do |
|---|---|
| "The updater does not answer" | `docker compose --profile updater ps`, `docker compose logs updater`; the token in `.env` and in the api must match |
| "This release publishes no digest" | the release predates auto-update; install it by hand or pick "None" verification |
| Status "Needs hands" (compose) | the rollback failed; the run log names the snapshot (`snapshots/...` in the `updater-data` volume), then `docker compose up -d` |
| Status "Needs hands" (Kubernetes) | the migrations changed the schema and the new version did not come up; the image was not rolled back, steps are in the run log (diagnose, fix the cause or restore the database and put the image back) |
| "The updater does not answer" (Kubernetes) | `kubectl get pods -l app.kubernetes.io/component=updater` and its log; `updater.token` and the `updater-token` key in the api Secret must match, the Role must allow the api Deployment |
| Run cancelled `precheck_failed` (Kubernetes) | the new image could not be pulled or the database is unreadable: `kubectl describe job` with the `hse-doc-studio/update-run` label; the api was not stopped |
| Update cancelled `unsupported_container_options` | a container has options the updater cannot carry over; update by hand |
| TAG in `.env` does not change | the file is not writable by the app user: `chmod o+w .env` |

Metrics for alerts: `hse_update_available`, `hse_update_updater_up`, `hse_update_last_run_success`, `hse_update_runs_total{result}`. Process settings: `HSE_STUDIO__SERVER_UPDATE__*` in the [reference](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md).
