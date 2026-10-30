---
title: Shared server
description: What server mode is, what it consists of, and where an operator or administrator starts.
tags:
  - Deployment
---

# Shared server

<p class="hds-lede">Server mode is for when more than one person uses the Studio: each has an account and their own projects, and heavy work (builds, packaging, conversion) runs on runners. The single-user local install is unchanged.</p>

!!! warning "Publish after the described code is merged"
    This section describes stage 2 server mode. Until the final slice lifts the startup ban, the api starts in `server` mode only with `HSE_STUDIO__AUTH__EXPERIMENTAL` and only on loopback. For a public server, wait for the release where the flag is no longer needed.

## What it consists of

| Part | Role |
|---|---|
| api | web UI, accounts, permissions, job queue; a single replica |
| Postgres | users, sessions, organizations, permissions, settings, secrets, the job queue |
| S3 (MinIO, Ceph, AWS) | job input blobs, finished PDFs and artifacts; a private bucket |
| projects volume | project sources, `projects_root/<id>` |
| runner | pulls jobs from the api over HTTPS and builds documents in sibling containers |
| LanguageTool, ONLYOFFICE, Ollama | optional services |

Redis is not needed: the job queue runs on Postgres.

## Roles

- The **operator** deploys and updates the server and keeps keys and backups. The operator is also the personal data controller.
- The **installation administrator** works in `/admin`: people, invitations, sign-in, mail, runners, audit.
- A **project member** sees only the projects they were added to. Someone else's project answers as if it did not exist, and `/admin` answers 404 to a non-admin.

## Where next

1. [Installation](install.md): compose or Helm, first run.
2. [People and sign-in](accounts.md): registration modes, invitations, mail, single sign-on (OIDC).
3. [Runners](runners.md): how to connect one and how isolation works.
4. [Security and personal data](security.md): runner threat model, what the administrator sees, operator duties.
5. [Backup, updates, key loss](operations.md).
6. [Environment variables](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md): the full settings reference (generated from the code, Russian descriptions).
