---
title: Server backups
description: Automatic encrypted backups of the database, files and objects; your own S3 from compose; restoring with the CLI.
tags:
  - Deployment
  - Operations
---

# Server backups

<p class="hds-lede">The Studio takes backups on a schedule, encrypts them on the server and stores them in S3 or a directory. Everything is configured in the admin, section "Backups". An operator restores with a CLI command: verification first, then an explicit confirmation.</p>

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

Restoring is a CLI command, not an admin action. It replaces the database the admin itself runs on, so it is safe only with api and runners stopped. In the admin every backup has a ready command with the values filled in.

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

## Environment

Schedule, destinations and retention live in the database and are edited in the admin. Only technical parameters are in the environment: `HSE_STUDIO__BACKUPS__ENABLED`, `..._LOCAL_ROOT`, `..._TMP_DIR` (needs room for the largest backup part), `..._PG_DUMP_BINARY`. The full list is in the [reference](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md).

The image has PostgreSQL clients 16 and 17; the Studio picks the same major version as the server. For an external Postgres of another version set `HSE_STUDIO__BACKUPS__PG_DUMP_BINARY` and `..._PG_RESTORE_BINARY`.
