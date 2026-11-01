---
title: Server backups
description: Automatic encrypted backups of the database, files and objects; your own S3 from compose; restoring with the CLI.
tags:
  - Deployment
  - Operations
---

# Server backups

<p class="hds-lede">The Studio takes backups on a schedule, encrypts them on the server and stores them in S3 or a directory. Everything is configured in the admin, section "Backups". You can restore from the admin (preview, confirmation, maintenance mode) or with a CLI command.</p>

Design and decisions: `docs/design/backups.md` in the repository (Russian).

## What a backup contains

| Part | Contents |
|---|---|
| database | `pg_dump` in one transaction: users, projects, permissions, settings, encrypted secrets |
| files | `data_dir`: project sources and their git, agent roles (`users/**`), the OpenPGP keyring (`gnupg/`), fonts. Excluded: `tmp/`, `jobs/` (build logs), local destinations and the object directory |
| objects | the whole object storage: job blobs, finished PDFs, submission archives |
| settings | a dump of installation settings and the destination list without keys (for humans) |

Order: database, files, objects. Files are copied while the api runs: project git is written atomically, so the copy is restorable but not an instant snapshot. A project created in the few seconds between the dump and the copy lands in the files without a database row; orphan garbage collection removes it.

Every backup is full. A backup without `manifest.json` is considered unfinished and is removed.

## Destinations

In the admin: **Backups, Destinations, Add.**

- **S3.** Endpoint, region, bucket, prefix, access key, secret key, path-style. Works with AWS, MinIO, Yandex Object Storage, Ceph, Selectel.
- **Server directory.** A subdirectory of `HSE_STUDIO__BACKUPS__LOCAL_ROOT` (default `data_dir/backups`). An arbitrary path cannot be entered, so the admin cannot write elsewhere on the filesystem. For another disk or NFS, mount it on this root.

You can have several destinations, one default; the schedule writes to it. A manual run from the admin also goes to the default; to back up to another one use `hse-doc-studio backup run --destination <name>`.

**Test connection** writes a probe object, reads it back, compares and deletes it. Keys are stored encrypted with the same `SECRETS_KEY` as other installation secrets and are never returned by the API or written to the audit log in full; only the tail of the access key is shown.

!!! warning "Backup storage must be separate"
    A backup on the same disk or in the same bucket as the data does not survive losing them. The admin warns when a destination equals the primary storage or sits on the same volume as the data. Another host or another provider is best.

## Your own S3 from compose

The overlay `deploy/server/compose.backup-s3.yml` starts MinIO (the `pgsty/minio` image, pinned tag) with its own volume, a private bucket and separate keys limited to that bucket.

```bash
cat backup-s3.env.example >> .env     # then fill in the passwords: openssl rand -hex 16
docker compose -f docker-compose.yml -f compose.backup-s3.yml up -d
```

Values for the destination form:

| Field | Value |
|---|---|
| Endpoint | `http://backup-minio:9000` |
| Region | `us-east-1` |
| Bucket | `hse-backups` (`BACKUP_S3_BUCKET`) |
| Path-style | on |
| Keys | `BACKUP_S3_ACCESS_KEY` and `BACKUP_S3_SECRET_KEY` from your `.env` |

The same values are in the "How to connect your own S3" hint in the form; "Fill in the values" populates the fields.

What the overlay does and does not do:

- The bucket is private, anonymous access is off. The backup keys differ from the primary bucket keys and from the MinIO root keys (`BACKUP_S3_ROOT_*`, which the Studio never gets).
- The S3 port (9000) and the console (9001) are open on the host loopback only (`BACKUP_S3_BIND`, `BACKUP_S3_PORT`, `BACKUP_S3_CONSOLE_PORT`).
- The `backup-minio-data` volume sits on the same disk as the primary one. This guards against corruption and mistakes, not against losing the host. For real protection run the overlay on another machine (`docker compose -p hse-backup-s3 -f compose.backup-s3.yml --env-file .env up -d`), put a TLS proxy in front of S3 and enter its address in the form.
- Versioning and object lock are off: the retention policy must be able to delete.

## Schedule and retention

- **Schedule:** an interval in hours (1 to 2160) or a five-field cron (minute, hour, day of month, month, day of week; lists, ranges, `*/5` steps), UTC. Missed firings collapse into one run. A failed run is not retried; admins get a notification.
- **Retention:** "keep latest N" and "keep days D". The N newest always stay; of the rest, those older than D days are deleted. Zero turns a rule off. The latest successful backup of a destination is never deleted. Only backups taken by this installation are touched.
- **One** run at a time. A run interrupted by an api stop is marked "interrupted" and its unfinished backup is removed.

## Encryption and integrity

All parts except `manifest.json` are encrypted (the manifest has no secrets: sizes, hashes, version, schema revision). AES-256-GCM in 1 MiB blocks; substitution, reordering and truncation of blocks are detected.

- **Installation key** (default): the key is derived from `SECRETS_KEY`. A backup is readable while the key exists. Store it separately from the backups.
- **Passphrase** (12+ characters): the backup does not depend on `SECRETS_KEY` and is readable only with the phrase. The phrase is stored encrypted on the server and never shown. Lose it and the backups cannot be opened.

The manifest records each part's size and sha256. After upload each part is read back and compared; the manifest is written last.

## Status, history, notifications

The "Backups" section shows the running job, history (time, destination, size, duration, error) and the backups found in a destination. A failed run creates a "Backup failed" notification in every admin's Inbox. Actions go to the audit log: `backup.destination_*`, `backup.settings_update`, `backup.run_start`, `backup.run_finish`, `backup.delete`.

## Restoring

### From the admin

**Backups, Destinations, Backups (button on a destination), Restore.** Steps:

1. **Preview** starts by itself and writes nothing: the manifest, key or passphrase, schema revision, sha256 and decryption of every part are checked; the current server state (users, projects, objects) is shown. It is a dry run: close the window if you do not want to restore.
2. **Confirmation.** Type the backup id. If the installation is not empty, also turn on "Overwrite existing data" (like `--overwrite`): otherwise the button stays disabled. The `projects/`, `users/`, `gnupg/` directories are not deleted but renamed to `*.before-restore-<time>`.
3. **Write in maintenance mode.** While writing, every request to the app gets 503 with code `maintenance`; background tasks and the database pool are stopped. Runners wait and retry. Status is available at the open `GET /api/maintenance`.
4. **Restart.** After success api exits by itself and compose (`restart: unless-stopped`) or Kubernetes starts it again. Sign in again: sessions now come from the backup. Without a supervisor set `HSE_STUDIO__BACKUPS__RESTART_AFTER_RESTORE=false` and restart api by hand.

If nothing was written yet (for example, something else is connected to the database), maintenance mode is left by itself and the installation is unchanged. If the write stopped midway, the mode stays: press "Retry the write" (safe, like re-running the CLI) or "Leave maintenance mode" and inspect the installation. If the process died mid-write it starts in maintenance mode; finish the restore with the CLI below. Restore from the admin is disabled with `HSE_STUDIO__BACKUPS__RESTORE_FROM_ADMIN=false`. It needs a single api replica. Actions go to the audit log: `backup.restore_preview`, `backup.restore_start`, `backup.restore_finish`, `backup.restore_cancel`.

### With the CLI

Use the CLI when the admin is unavailable; it is the strictest path and is safe only with api and runners stopped. In the admin every backup has a ready command with the values filled in.

```bash
# 1. a fresh installation with the same SECRETS_KEY and an image at least as new as the backup; run it once, then stop api
docker compose stop api runner

# 2. inspect and verify (writes nothing)
export BACKUP_S3_ACCESS_KEY=... BACKUP_S3_SECRET_KEY=...
docker compose run --rm --no-deps -e BACKUP_S3_ACCESS_KEY -e BACKUP_S3_SECRET_KEY api \
  hse-doc-studio backup list --s3-endpoint http://backup-minio:9000 --s3-bucket hse-backups --s3-prefix studio --s3-path-style
docker compose run --rm --no-deps -e BACKUP_S3_ACCESS_KEY -e BACKUP_S3_SECRET_KEY api \
  hse-doc-studio backup restore --s3-endpoint ... --s3-bucket hse-backups --s3-prefix studio --s3-path-style --backup-id <id>

# 3. restore
...the same restore with --apply

# 4. start api, then runners
docker compose up -d api runner
```

Backup source: `--from-dir <backup folder>`, or `--s3-bucket` with `--s3-endpoint`, `--s3-prefix`, `--s3-region`, `--s3-path-style` and keys in `BACKUP_S3_ACCESS_KEY` and `BACKUP_S3_SECRET_KEY`, or `--destination <name>` (from the database of a live installation). Passphrase: `BACKUP_PASSPHRASE` or `--passphrase-file`. Secrets are never passed as arguments.

What is checked, and what the command will not do without your say-so:

1. The manifest is read, the key or phrase matches (`key_check`), the schema revision is known to the image. A backup newer than the image is rejected: run the same or a newer release.
2. Every part is downloaded, checked by sha256 and decrypted. Without `--apply` it ends here.
3. With `--apply` the command refuses to run if an api or another application is connected to the database, or if the installation is not empty (users, projects or objects exist). A non-empty installation can only be overwritten with `--overwrite`; on a terminal you must also type `overwrite`. The `projects/`, `users/`, `gnupg/` directories are not deleted but renamed to `*.before-restore-<time>`.
4. The database is restored in one transaction (all or nothing), then files and objects. The command can be re-run.

After restoring: `hse-doc-studio db check`, `GET /health/ready`, sign in as admin, open a project, build a PDF. See the [manual procedure](operations.md) for orphan garbage collection caveats.

Test restores on a clean machine regularly: a backup you never restored is not a backup. `hse-doc-studio backup verify` can run from the operator's cron.

## Kubernetes (Helm)

Destinations and the schedule live in the database, so the chart passes initial values through the environment (`HSE_STUDIO__BACKUPS__PROVISION__*`). On startup the api, under the leader lock, creates the default destination and the schedule settings **only if there are no destinations yet**. After that everything is edited in the admin UI and restarts do not overwrite your changes. If you delete all destinations they are created again on the next start.

```yaml
backups:
  enabled: true
  local:                      # volume for local backups: PVC <release>-backups mounted at /backups
    enabled: true
    persistence: {size: 100Gi, storageClassName: slow}
  destination:
    kind: s3                  # or local
    name: offsite
    endpoint: https://s3.example.org
    bucket: studio-backups
    prefix: studio
    accessKey: ...            # better in a Secret: backup-access-key
    secretKey: ...            # backup-secret-key
  schedule: {kind: cron, cron: "30 2 * * *", keepLast: 14, keepDays: 60}
  encryptionMode: installation   # or passphrase + backups.passphrase (Secret: backup-passphrase)
```

- The backups PVC carries `helm.sh/resource-policy: keep`, so `helm uninstall` does not delete it. Use another storage class or an external S3: a backup on the data volume does not survive its loss.
- Secrets can stay out of values: create your own Secret (`secrets.existingSecret`) with the keys `backup-access-key`, `backup-secret-key`, `backup-passphrase`.
- `backups.enabled=false` (default): the chart adds nothing, destinations are created in the admin UI.
- The migration Job does not receive backup settings.

Restore in Kubernetes is a CLI command run with the api stopped: `kubectl scale deploy/<release>-hse-doc-studio-api --replicas=0`, then a one-off pod with the same image, Secret and volumes (`kubectl run` or a Job running `hse-doc-studio backup restore ...`), then `--replicas=1`. Restore from the admin also works in Kubernetes: after the write the pod exits and the Deployment starts it again (same volume and Secret).

## Metrics and alerts

`/metrics` (requires `METRICS_TOKEN`) exposes backup state. Values refresh on every scheduler tick (30 seconds by default) and at startup; counters come from the runs table, so they survive an api restart.

| Metric | Meaning |
|---|---|
| `hse_backup_enabled` | schedule is on (1) or off (0) |
| `hse_backup_running` | a backup is running now |
| `hse_backup_last_success_timestamp_seconds` | finish time of the last success (0 if there never was one) |
| `hse_backup_last_success_age_seconds` | age of the last success, computed on every scrape; huge if there was none |
| `hse_backup_last_duration_seconds`, `hse_backup_last_size_bytes` | duration and size of the last successful backup |
| `hse_backup_last_run_ok` | the last finished run succeeded (1) or not (0) |
| `hse_backup_runs_total{status}` | runs by status: `running`, `ok`, `failed`, `interrupted` |
| `hse_backup_failures_total` | runs with status `failed`, all time |

Ready-made alert rules: `deploy/monitoring/backup-alerts.yml` (no success for over 26 hours while the schedule is on, last run failed, failures within a day, size halved). Grafana dashboard: `deploy/monitoring/backup-dashboard.json`. Tune the 26-hour threshold to your schedule.

## Environment

Schedule, destinations and retention live in the database and are edited in the admin. Only technical parameters are in the environment: `HSE_STUDIO__BACKUPS__ENABLED`, `..._LOCAL_ROOT`, `..._TMP_DIR` (needs room for the largest backup part), `..._PG_DUMP_BINARY`. The full list is in the [reference](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md).

The image has PostgreSQL clients 16 and 17; the Studio picks the same major version as the server. For an external Postgres of another version set `HSE_STUDIO__BACKUPS__PG_DUMP_BINARY` and `..._PG_RESTORE_BINARY`.
