---
title: Server self-diagnostics
description: The checks page for the database, storage, runners, disk, certificates, backups, mail and background jobs; thresholds, notifications, monitoring.
tags:
  - Deployment
  - Operations
---

# Server self-diagnostics

<p class="hds-lede">Every few minutes the server checks its database, storage, runners, disk, certificates, backups, mail and background jobs. Each check has a status, a reason and a hint on what to do. Admins get a notification only when a problem persists.</p>

Design and decisions: `docs/design/self-diagnostics.md` in the repository.

## Where to look

In the admin: **Self-diagnostics** (`/admin/diagnostics`). The overall result is on top, the checks follow by group. “Check now” runs everything, “Check” on a row runs one check. A manual run refreshes the page but sends no notifications.

Statuses: **OK**, **Warning** (works, but will soon be bad), **Failure** (work is broken or data is at risk). “Not configured” means the subsystem does not exist (for example SMTP); such a check does not count towards the overall result.

## What is checked

| Check | What it looks at | What to do |
|---|---|---|
| Database | reachability, version, latency | start Postgres, check `HSE_STUDIO__DB__*`, disk load |
| Database migrations | revision in the database against the image | restart api (it migrates itself); an image older than the database means run a fresh image |
| Object storage | write, read and delete of a probe object; whether runners outside the server network exist while S3 has only an internal address | check keys, bucket and free space in `HSE_STUDIO__S3__*`; set `HSE_STUDIO__S3__PUBLIC_ENDPOINT` or the `proxy` mode (section “Runners outside the server network” in Runners) |
| Disk and data retention | volumes and database, as the space guard sees them, cleanup errors | shorten retention in “Data retention”, grow the volume |
| Runners | are shared runners online | register or restart a runner |
| Queue and stuck jobs | queue wait, jobs with an expired lease | add runners, turn on autoscaling |
| Background jobs | is there a leader, are jobs stuck | restart api, check the database link |
| Certificates | expiry of the public address (`auth.public_url`) and S3 | renew the certificate, check auto-renewal |
| Backups | age of the last successful one, last attempt | take one by hand, check destination and schedule |
| Mail (SMTP) | connect and sign in, no mail sent | check host, port and password |

The exact hint is shown on the page under each problem.

## Accepting a warning on purpose

If you knowingly live with a warning (you do not back up, you do not connect public runners), you can accept it: the row has an **"I accept: this is on purpose"** button. The dialog asks for a reason (up to 200 characters) and, optionally, a term: indefinitely (default) or until a date.

An accepted warning:

- gets a grey "Accepted" status with the reason, who accepted it and when; it stays out of the page total, the dot on "Self-diagnostics" in the menu and the "Needs attention" line on the admin overview; the "no runners" and "no backup destination" banners are replaced by a grey line with the reason;
- sends no notifications to admins;
- stays in the metrics, flagged: `hse_diag_check_status` shows the real status while `hse_diag_check_accepted{check}` is `1`; `hse_diag_overall_status` ignores accepted checks; the public `/health/diagnostics` shows `accepted` for such a check;
- is silent while the cause is there. If you later enable backups or connect a runner, the record stays but silences nothing; if the warning comes back, it is silenced again until you remove the record or the term ends.

All accepted warnings are listed in the **"Accepted warnings"** section at the bottom of the page; **"Bring the warning back"** removes the acceptance (also on the check row and in the grey banners). Accepting and undoing are written to the audit log (`diagnostics.accept`, `diagnostics.accept_revoke`: who, when, reason, term), are available only to the installation admin and are stored in the installation settings (`diagnostics.accepted`), no migration needed.

| Can be accepted (warning only) | Can never be accepted |
|---|---|
| Runners: no shared runners, or none online (while the queue is empty) | Database, migrations, disk and data retention |
| Object storage: no public S3 address for runners outside the server network | Object storage: unreachable, cannot write or read |
| Backups: switched off or no destination | Queue and stuck jobs, background tasks (leader) |
| Mail: SMTP unreachable | Certificate expiry (expiring or expired); backups that are configured but stale or failing |
| Certificates: the address could not be checked from the container | Any failure (`fail`), including those of acceptable checks |

If an accepted check gets worse to a failure or its cause changes (for example backups are configured but stale), the acceptance does not apply and the warning shows as usual.

### Accepted backups and updates

When "no backups" is accepted, a manual update on Kubernetes (the `kubernetes` executor, which has no database snapshot) no longer asks you to confirm the risk with a switch: the dialog shows one line, "Backups are off on purpose, reason: ...". Auto-install without a backup still does not start: the acceptance does not enable it, and admins get the update notification.

## Thresholds and notifications

At the bottom of the page: database and storage latency, queue wait, job overdue, certificate expiry, backup age. “Reset to defaults” restores factory values. Disk thresholds are shared with the space guard and edited in “Data retention”.

| Setting | Default | Meaning |
|---|---|---|
| Status confirmation | 2 passes | how many checks in a row a status must hold before a notification |
| Reminder | 24 h | how often to repeat about the same problem |
| Notify admins | on | an inbox message on a switch to warning or failure and on recovery |

A single failure or a flapping status raises nothing. The notification opens the self-diagnostics page.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `HSE_STUDIO__DIAGNOSTICS__ENABLED` | `true` | scheduled check under the leader lock |
| `HSE_STUDIO__DIAGNOSTICS__INTERVAL_S` | `300` | check period |
| `HSE_STUDIO__DIAGNOSTICS__CHECK_TIMEOUT_S` | `20` | time limit of one check |
| `HSE_STUDIO__DIAGNOSTICS__PUBLIC_ENDPOINT` | `false` | open `/health/diagnostics` for monitoring |

## External monitoring

**Public endpoint.** With `HSE_STUDIO__DIAGNOSTICS__PUBLIC_ENDPOINT=true`, `GET /health/diagnostics` is available without sign-in:

```json
{"status": "warn", "checked_at": "2026-11-05T10:00:01+00:00", "checks": {"database": "ok", "disk": "warn"}}
```

Only statuses by check id: no reasons, values or addresses. The response code is `200` for `ok` and `warn`, `503` for `fail` and while there are no results yet (`"status": "unknown"`). Point UptimeRobot, Gatus or Zabbix at it.

**Prometheus metrics** (`/metrics`, with the `HSE_STUDIO__OBSERVABILITY__METRICS_TOKEN` token):

| Metric | Meaning |
|---|---|
| `hse_diag_check_status{check}` | 0 OK, 1 warning, 2 failure (an accepted check is shown as is) |
| `hse_diag_check_accepted{check}` | 1 when the warning is accepted on purpose |
| `hse_diag_check_last_timestamp_seconds{check}` | when the check last ran |
| `hse_diag_check_duration_seconds{check}` | duration of the last check |
| `hse_diag_overall_status` | overall result without accepted warnings |

Metrics read the process cache and are fresh on the leader and on instances whose page was opened; with several instances scrape all of them and take the maximum. Example rule: `max(hse_diag_overall_status) >= 2` for 10 minutes. Build per-check alerts so that accepted checks do not fire: `hse_diag_check_status >= 1 unless on(check) hse_diag_check_accepted == 1`.

## If the page is empty

“No checks have run yet” on a freshly started installation is normal: the first pass runs seconds after the leader starts. If it stays so, look at the “Background jobs” check (press “Check now”) and `docker compose logs api`.
