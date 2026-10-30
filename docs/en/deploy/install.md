---
title: Server installation
description: Deploying the shared server with docker compose or Helm, and the first run that creates the administrator.
tags:
  - Deployment
  - Docker
  - Kubernetes
---

# Server installation

<p class="hds-lede">Two ways: docker compose on one machine, or the Helm chart for Kubernetes. Both bring up the api, Postgres, S3 and a runner.</p>

## What to prepare

- a domain and a TLS-terminating reverse proxy with an address like `https://studio.example.org`;
- a Docker machine for the api and a separate, ideally dedicated one for the runner: the Docker socket is root on the host;
- two secrets: the Postgres password and the secrets encryption key (Fernet), see [key loss](operations.md).

## docker compose

The files are in the repository under `deploy/server`.

```bash
cd deploy/server
cp .env.example .env              # fill in the required values, hints are inside the file
sudo mkdir -p /var/lib/hse-runner # runner data directory
docker compose up -d
docker compose --profile services up -d   # add LanguageTool and ONLYOFFICE
```

Required values in `.env`:

| Variable | Purpose |
|---|---|
| `PUBLIC_URL` | external address: its scheme sets the cookie `Secure` flag, and it joins the allowed Origins |
| `POSTGRES_PASSWORD` | database password |
| `SECRETS_KEY` | Fernet key that encrypts secrets in the database |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | MinIO credentials and the private bucket name |
| `RUNNER_BOOTSTRAP_TOKEN` | one-time registration token for the first runner |
| `TRUSTED_PROXIES` | your reverse proxy addresses as a JSON list, used to determine the client address |

The runner directory (`RUNNER_DATA_DIR`) is mounted at the same path on the host and in the container so sibling build containers see the files. Its owner is the image user `app` (uid 10001).

### Reverse proxy

The runner holds a poll request for up to 25 seconds. Set a read timeout of at least 60 seconds and turn response buffering off. For nginx: `proxy_read_timeout 75s; proxy_buffering off;`.

## Kubernetes

The chart is in `deploy/helm/hse-doc-studio`: the api (one replica, Recreate strategy), a migrations Job before upgrade, a runner, ingress, Secret and PVC. Postgres and S3 are external. Prefer your own Secret (`secrets.existingSecret`) over values. Details and limits are in the chart README.

## First run

1. Open `PUBLIC_URL`. While there is no administrator, the Studio shows the first-run wizard.
2. If the server listens on more than loopback, the wizard asks for the setup token. It is printed in the api log: `docker compose logs api | grep -i setup`.
3. Create the administrator, choose the registration mode and configure mail if needed.
4. In the admin area open the runners section and check that the runner is registered and takes jobs.

Without the wizard you can create the administrator from the environment: `HSE_STUDIO__AUTH__ADMIN_EMAIL` and `HSE_STUDIO__AUTH__ADMIN_PASSWORD` (or `..._PASSWORD_FILE`). Creation is idempotent: an existing administrator's password is not changed. This is the recommended path for automation.

Settings fixed in the environment (registration mode, domains, password, approval) win over database values and appear locked in the admin area.

## Checks

- `GET /health` answers `ok` or `fail`, with no details.
- `GET /health/ready` with `Authorization: Bearer <HEALTH_TOKEN>` returns check details. Without the token only an administrator sees them.
- `/metrics` answers 404 until `METRICS_TOKEN` is set.
- Database schema: `hse-doc-studio db check` (exit code 1 if the database is not at the latest revision).

## Restricting the admin area

`HSE_STUDIO__ADMIN__ALLOWED_HOSTS` and `HSE_STUDIO__ADMIN__ALLOWED_CIDRS` narrow where `/admin` can be opened from. If both are set, a request must pass both.
