---
title: Security and personal data
description: Runner threat model, trust boundaries, what the administrator sees and what the operator must do as a personal data controller.
tags:
  - Deployment
  - Security
---

# Security and personal data

## Runner threat model

Users write the sources and build settings, so the runner processes **untrusted input**. A LaTeX build can call external programs and read files, so the runner is built like this:

| Threat | Mitigation |
|---|---|
| A build reads or corrupts neighbouring projects | each job gets its own workspace; input files are copied, not linked, and hashes are re-checked; the blob cache is read-only |
| Build output replaces files or points outside | the output collector accepts only regular files, symlinks are rejected |
| A build reaches the network and internal services | the build container runs without runner secrets and without job tokens |
| A stolen runner token | stored as a hash in the database, rotated and revoked in the admin area; a runner gets only what is in the queue |
| A foreign runner plants artifacts | the api verifies and applies results; the job token (HMAC) is limited to one job and attempt |
| Escaping the build container | see the residual risk below |

### Residual risk: the Docker socket

The runner drives sibling containers through `/var/run/docker.sock`. That equals root on the runner host. Therefore:

- treat the runner host as trusted infrastructure, separate from the api and database;
- prefer rootless Docker, sysbox or a dedicated virtual machine;
- the api has no Docker access and must not get any;
- on Kubernetes use the `kubernetes` executor (a pod per job, no socket or hostPath, Pod Security restricted, no network); for shared installations add a gVisor or Kata RuntimeClass (`runner.kubernetes.runtimeClassName`). See "Runners" and `docs/design/k8s-runner.md`.

### Updating from the admin in Kubernetes

The `kubernetes` executor (`updater.enabled=true`, off by default) gets a ServiceAccount token with a role strictly on the release namespace: `get` and `patch` on one api Deployment by name, Jobs, reading pods and their logs; no secrets and no `ClusterRole`. The api has none of these rights: it only creates a "update to version X" record, and the updater takes the image from the Deployment's own repository and checks it against the release digest. Still, the updater token can replace the api image, so grant it nothing more, keep `updater.token` in a Secret, and for locked-down installs leave the executor off (update with `helm upgrade`). See [Auto-update](auto-update.md#kubernetes).

## Trust boundaries

- **Project members** see only their projects. Someone else's project answers as non-existent (404); a missing role gives 403.
- **The installation administrator** manages people and settings but has no implicit access to project contents. The two bypass paths (password reset link and adding oneself to an organization) are break-glass: with confirmation, an audit entry and a notification.
- **Project permissions** live only in the database. `project.json` carries them as a hint, and the database value always overwrites the file; a `project.json` arriving through git does not change permissions.
- **Outgoing requests** from users (git, OIDC, AI providers) pass a policy: loopback, link-local, private networks and cloud metadata addresses are blocked; internal hosts are opened through `HSE_STUDIO__EGRESS__ALLOWLIST`.
- **User files** are served with `nosniff`, a type allowlist and a CSP sandbox.
- **Secrets in the database** (git tokens, SMTP password, OIDC secret, AI keys) are encrypted and bound to their record; without `SECRETS_KEY` they cannot be read.
- **The admin area** can be restricted by host name and network.
- **The MCP server** (`/mcp`, [AI clients](../workbench/mcp.md)) is off by default and accepts only a personal token with the `mcp` permission; browser cookies are not accepted. A client acts with the token owner's rights and quotas; dangerous and admin tools are enabled explicitly, and every call is written to the audit log (`mcp.call`).
- **The OpenPGP keyring is shared.** Secret keys and uploaded public keys live in one server keyring (`data_dir/gnupg`), not per person: key records are tied to their owner in the database, but the keyring itself is common and signature checks see everyone's keys. If you need separation, do not allow secret keys on the server (admin, “Signing keys”; forbidden by default): then an OpenPGP secret key cannot be created or uploaded, and only public keys for checking signatures enter the keyring. Keys created before the ban stay in the keyring and are counted in the admin, but cannot sign until storage is allowed again. An OpenPGP secret key is protected only by its own passphrase, `SECRETS_KEY` does not encrypt it. Agent personas, by contrast, are separate: `data_dir/users/<id hash>/`.

## Personal data

!!! note "The operator is you"
    The author runs no public service. Whoever deployed the server is the controller of their users' personal data and is responsible for its processing.

What is stored:

| Data | Where |
|---|---|
| name, mail address, password hash, organization info | Postgres |
| sessions (client address, device), audit log | Postgres, audit retention is configurable |
| thesis texts, attachments, builds | projects volume and S3 |
| AI agent chats, settings, keys | Postgres, keys are encrypted |

What the operator must do:

1. Tell users what is processed and why, and appoint a responsible person. Applicable law (for example GDPR or Russian 152-FZ) depends on your case; check with a lawyer.
2. Keep data where your organization allows it; Postgres and S3 run on your side.
3. Set retention: `AUDIT_RETENTION_DAYS`, `PROJECT_RETENTION_DAYS` (a deleted project is erased from the volume and catalog after the period).
4. Protect backups as strictly as the data itself.
5. Choose AI providers deliberately: project text goes to the selected provider. A local Ollama keeps data with you. The list of outside calls: [What goes over the network](../reference/privacy.md).

An account is disabled in the admin area; projects are deleted by their owner or by the retention period.
