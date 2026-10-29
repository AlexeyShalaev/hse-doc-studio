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
