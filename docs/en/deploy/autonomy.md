---
title: Autonomous operation and data retention
description: How the server cleans growing data on its own, rotates logs and protects itself from running out of disk.
tags:
  - Deployment
  - Operations
---

# Autonomous operation and data retention

Everything that grows on its own has a retention period and a background cleanup. The **Data retention** admin page (`/admin/data`) shows all sources, their size, retention and the last cleanup.

| What | Default | Bounds in admin |
|---|---|---|
| audit log | 365 days | 90 days to 10 years; never cleaned manually |
| AI call log | 90 days | 30 days to 5 years |
| jobs and build logs | 30 days | 1 to 365 |
| inbox | 90 days | 14 to 730 |
| invitations, access requests, transfers | 90 days | 30 to 730 |
| revoked and expired share links | 180 days | 30 to 1095 |
| co-editing state on disk | 90 days idle | 7 to 365 |
| guest sessions | 7 days after expiry | fixed |

The audit and AI logs are split into monthly Postgres partitions: old partitions are dropped whole and new ones are created ahead of time. Other tables are cleaned in batches with a pause. The task runs on the leader instance hourly.

Container logs rotate (`json-file`, 5 files of 10 MB per container; `LOG_MAX_SIZE` and `LOG_MAX_FILE` in `.env`). Every 5 minutes the server checks the data volumes and the database size; at 80% admins get an inbox warning, at 90% a safe mode starts: uploads over 1 MB are refused with `507 storage_critical` while small edits, sign-in, admin and runners keep working. Thresholds are editable on the page. Metrics: `hse_lifecycle_*`, `hse_storage_*` in `/metrics`.

Upgrade note: migration `lc_02_partition_logs` attaches the old tables as partitions without copying rows; inserts into the logs wait about a second per million rows. For huge logs pre-build the index: `CREATE UNIQUE INDEX CONCURRENTLY audit_log_idat_uq ON audit_log (id, at);` (same for `ai_usage`).
