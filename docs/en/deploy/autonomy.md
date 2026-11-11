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

## Free up space now { #free-up-space }

The **Free up space** button in the header of the **Storage** page (`/admin/storage`) runs every manual cleanup of **Data retention** in a row without waiting for the hourly tick: the AI call log, build jobs and logs, the inbox, invitations and access requests, share links, guest sessions and the co-editing state. Every source is cleaned by its own period with the same run as on schedule and on **Clean now**, with the same time budget.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/admin/storage</span></div>
    <img src="../assets/shots/storage-free.en.light.webp#only-light" alt="Free up space now?">
    <img src="../assets/shots/storage-free.en.dark.webp#only-dark" alt="Free up space now?">
  </div>
  <figcaption>the confirmation: period, record count and size per source, and what the cleanup leaves out</figcaption>
</figure>

- **Preview.** Before the start the server counts how many records or files are past the period in every source. Counting stops at 100,000 and takes at most 3 seconds per source: beyond that it says "more than 100,000", on timeout "could not count". When there is nothing to delete, the confirm button is disabled.
- **Progress and result.** The run is a task on the server, so the window can be closed: progress and the result show in a banner under the header. The result separates deleted records from space freed on disk. A Postgres `DELETE` frees space inside the database; database files shrink only when a partition is dropped. A source that ran out of budget finishes on the scheduled tick.
- **Stop and failure.** "Stop after the current source" stops the run between sources. A run not updated for 5 minutes (the api restarted) is marked interrupted.
- **One at a time.** A second start answers 409 `lifecycle_sweep_busy`. The audit log gets `lifecycle.sweep`, `lifecycle.sweep_cancel` and `lifecycle.swept`; `/metrics` counts `hse_lifecycle_sweeps_total{status}`.
- **Not included.** The audit log (never cleaned manually), background cleanups with their own schedule (unreferenced blobs, orphans, the project bin, sessions and tokens), runner disks and images on Kubernetes nodes. Runner disks are cleaned one at a time from the admin area: [Runner disk](runners.md#runner-disk).

Below the Storage cards, **Where else to free up space** links to Data retention and summarises shared runner disks: how much they can free and up to three runners with the most. Runners below 0.22.0 do not report their disk, and the block suggests updating them.

Endpoints: `GET /api/admin/data-lifecycle/sweep/preview`, `POST /api/admin/data-lifecycle/sweep`, `GET /api/admin/data-lifecycle/sweep`, `POST /api/admin/data-lifecycle/sweep/{id}/cancel`. Runs (`lifecycle_sweeps`, the latest 20) and runner commands (`runner_commands`, the latest 20 per runner) are capped on write and show on the Data retention page.

## Logs, disk space and metrics

Container logs rotate (`json-file`, 5 files of 10 MB per container; `LOG_MAX_SIZE` and `LOG_MAX_FILE` in `.env`). Every 5 minutes the server checks the data volumes and the database size; at 80% admins get an inbox warning, at 90% a safe mode starts: uploads over 1 MB are refused with `507 storage_critical` while small edits, sign-in, admin and runners keep working. Thresholds are editable on the page. Metrics: `hse_lifecycle_*`, `hse_storage_*` in `/metrics`.

Upgrade note: migration `lc_02_partition_logs` attaches the old tables as partitions without copying rows; inserts into the logs wait about a second per million rows. For huge logs pre-build the index: `CREATE UNIQUE INDEX CONCURRENTLY audit_log_idat_uq ON audit_log (id, at);` (same for `ai_usage`).

Server health is visible on the **Self-diagnostics** page (`/admin/diagnostics`); disk space from this subsystem is one of its checks, with the same thresholds. See [Server self-diagnostics](diagnostics.md).
