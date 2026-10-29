---
title: Runners
description: How to connect a runner, issue, rotate and revoke its token, and how jobs are executed.
tags:
  - Deployment
  - Runner
---

# Runners

<p class="hds-lede">A runner executes builds, submission packaging, signature checks and office conversions. It polls the api over HTTPS itself, so no inbound connection to the runner is needed.</p>

## How a job runs

1. The api puts the job into the Postgres queue: fair per user, and identical waiting jobs supersede each other.
2. A runner takes a job by long polling and gets a 45-second lease; while alive it renews it every 10 seconds. A dead runner loses the job and it returns to the queue, up to two retries.
3. The input is a file manifest plus blobs by sha256. The runner downloads what is missing into its cache and verifies the hashes.
4. The runner sends the result to the api, which verifies and applies it. A runner never writes to the database or the projects volume directly.

## Connecting a runner

1. In the admin area open Runners and issue a **registration token**: a label, a lifetime (24 hours by default) and a number of uses.
2. On the runner machine set the environment:

   | Variable | Value |
   |---|---|
   | `HSE_RUNNER__API_URL` | Studio address, `https://studio.example.org` |
   | `HSE_RUNNER__TOKEN` | registration token |
   | `HSE_RUNNER__NAME` | name in the list (hostname by default) |
   | `HSE_RUNNER__CONCURRENCY` | jobs at the same time |
   | `HSE_RUNNER__DATA_DIR` | working folders and the blob cache |
   | `HSE_RUNNER__OFFICE_URL` | Gotenberg address; without it office jobs are not taken |

3. Run `hse-doc-studio runner` (the same command in the image).
4. The runner exchanges the registration token for its own and stores it in `data_dir/identity.json`. After that `HSE_RUNNER__TOKEN` can be removed from the environment.

In compose the first runner registers with `RUNNER_BOOTSTRAP_TOKEN`.

## Management

The list shows version, tags, capacity and last poll time.

- **Pause** stops handing out new jobs; running ones finish.
- **Token rotation** issues a new runner token; the old one stops working. Put the new one into `identity.json`.
- **Revoke** closes the runner's access for good. A registration token can also be revoked before use.
- The api and runner versions are checked at registration; an incompatible runner is rejected.

## Scaling

Several runners on different machines work together. Two replicas on one machine need different data directories. These are installation-level runners: there are no per-user or per-organization runners.
