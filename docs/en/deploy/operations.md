---
title: Backup, updates, key loss
description: What to back up, how to update the server, what happens when the encryption key is lost, and how to rotate it.
tags:
  - Deployment
  - Operations
---

# Backup, updates, key loss

## What to back up

| What | How |
|---|---|
| database | `docker compose exec postgres pg_dump -U studio studio > studio.sql` |
| project sources | the `api-data` volume (`projects_root`) |
| blobs, job inputs and outputs | the S3 bucket or the `minio-data` volume |
| ONLYOFFICE | the `onlyoffice-data` volume, if the service is on |
| the `SECRETS_KEY` key | **separately** from dumps, in a secrets manager |

Back up the database and the projects volume consistently: stop writes or snapshot both. Test a restore on an empty machine from time to time.

## Updating

compose: change `TAG`, then `docker compose pull && docker compose up -d`. The api runs database migrations at startup under an advisory lock.

Helm: `helm upgrade`; the migrations Job runs before the upgrade. Set `secrets.existingSecret` so the Job sees current secrets.

Take a backup first. Update runners together with the api: an incompatible version is rejected at registration. Schema check: `hse-doc-studio db current` and `hse-doc-studio db check`.

One api replica runs at a time, so an update briefly interrupts access.

## Version compatibility and rollback

Migrations follow expand/contract: release N only adds (tables, columns with a default, indexes), and removal or tightening waits for release N+1. So the N-1 image keeps working on a database already upgraded to N. Tests enforce it: an N-1 to N migration on a populated database and a ban on destructive steps in `upgrade()`.

- **Runner and api.** A runner announces its protocol version at registration; a mismatch is rejected with `runner_protocol_unsupported`. Update the api first, then the runners of the same release.
- **Image rollback.** Restore the previous `TAG` (or `helm rollback`). Do not roll the schema back: image N-1 works with database N. If a release changed data irreversibly, restore the backup taken before the update (see below).
- **Database newer than the image.** An older image that sees a revision it does not know refuses to start with `db_ahead`. This is a guard: start an image of the same or a newer release.
- **Database older than the image.** A backup from an earlier release started with a newer image is caught up by migrations at startup.

## Restoring from a backup

The three stores (database, projects volume, S3) must come from the same moment. Order:

1. Stop the api and runners: `docker compose stop api runner`.
2. Bring back `SECRETS_KEY` from the secrets manager. Without it the secrets in the database are unreadable (see below).
3. Restore the database into an empty one: `docker compose exec -T postgres psql -U studio studio < studio.sql`.
4. Restore the `api-data` volume and the S3 bucket (or the `minio-data` volume) from snapshots of the same moment.
5. Start the api with an image of the same or a newer release than the backup. Migrations run at startup.
6. Start the runners after the api.

Checks after the restore:

- `hse-doc-studio db current` and `hse-doc-studio db check` show head with no drift;
- `GET /health/ready` with `HEALTH_TOKEN` is green for every check;
- sign in as an administrator, open a project, build a PDF: the build reads blobs from S3 and confirms their hashes;
- if the database is newer than the bucket (blobs in the registry are missing from S3), a build that needs a missing file fails with a manifest error. Extra blobs in the bucket are harmless: cleanup removes them.

If the database is newer than the projects volume, open the affected projects and re-save the files from users' working copies; if the volume is newer than the database, new projects are missing from the database and must be imported again.

## Key loss

`SECRETS_KEY` (Fernet) encrypts secrets in the database: git tokens, the SMTP password, OIDC secrets, AI provider keys and signing. The key is never stored next to the database so a stolen dump does not reveal secrets.

**If the key is lost, the secrets cannot be recovered.** What happens:

- users, projects, permissions, builds and the documents themselves are **not affected**: this key does not encrypt them;
- stored secrets become unreadable: SMTP, OIDC, git tokens, AI keys.

Recovery:

1. Generate a new key and set it as `SECRETS_KEY`.
2. Re-enter the SMTP password and OIDC secrets in the admin area.
3. Users re-enter their git tokens and AI keys in settings.
4. Keep a copy of the new key outside the database backup.

## Rotating the key

If the key must be replaced and the old one is known:

1. Set the new key as primary and pass the previous one in `HSE_STUDIO__SECRETS__RETIRED_KEYS`.
2. Check the volume: `hse-doc-studio secrets reencrypt --dry-run`.
3. Run `hse-doc-studio secrets reencrypt`. It prints the number of re-encrypted and unreadable records. If it reports a record changed during the run, run it again.
4. When nothing is unreadable, remove the previous key from `RETIRED_KEYS`.

## When something goes wrong

- a start without the database lists what is missing; read the api log;
- `GET /health/ready` with `HEALTH_TOKEN` shows which check is red;
- a runner takes no jobs: check the runners section in the admin area, pause, version and access to `API_URL`; behind a proxy make sure the timeout is at least 60 seconds.
