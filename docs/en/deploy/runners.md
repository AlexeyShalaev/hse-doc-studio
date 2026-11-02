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
- **Token rotation** issues a new runner token; the old one stops working. Pass the new token as `HSE_RUNNER__RUNNER_TOKEN`: it overrides `identity.json`.
- **Revoke** closes the runner's access for good. A registration token can also be revoked before use.
- The api and runner versions are checked at registration; an incompatible runner is rejected.
- After registering, a new runner negotiates capabilities with the api (`/announce`): AI relay, separate slots for it and a stop notice. With an older api that does not know this call the runner keeps working as before, without the relay; an older runner works with a newer api too.

## AI through your own runner

The server never reaches into users' internal networks. To use a model on your own hardware (Ollama, vLLM, LM Studio, any OpenAI-compatible endpoint), the owner of a personal runner declares endpoints in the runner's environment and adds a "Via my runner" provider on the site. The server only knows the endpoint name; the URL and key stay with the runner.

| Variable | Value |
|---|---|
| `HSE_RUNNER__AI_ENDPOINTS` | JSON list of endpoints: `[{"name":"ollama","url":"http://localhost:11434/v1","flavor":"ollama"},{"name":"vllm","url":"http://gpu.lan:8000/v1","key_env":"VLLM_API_KEY"}]` |
| `HSE_RUNNER__AI_CONCURRENCY` | how many model requests the runner serves at once (default 2), separate from builds |
| `HSE_RUNNER__RELAY_MAX_RESPONSE_BYTES` | model answer limit (default 64 MiB) |

- `name`: lowercase latin letters, digits, `-` and `_`, up to 32 characters; this is how the endpoint is called in the provider form.
- `flavor`: `openai` (default) or `ollama` (no `tool_choice` and `stream_options`, as Ollama requires).
- `key_env`: name of the runner's environment variable holding the model key; the key never reaches the server. The runner rejects a user or password inside `url`: endpoints are written to the log at startup.
- The runner only calls declared endpoints and only the paths `models`, `chat/completions`, `completions`, `embeddings`; server headers are not forwarded and redirects are not followed.
- Only the runner owner can relay through it. Without declared endpoints the runner takes no relay jobs.

api-side limits: `HSE_STUDIO__JOBS__RELAY_PICKUP_S` (how long to wait for the runner to take the request), `HSE_STUDIO__JOBS__RELAY_MAX_REQUEST_BYTES`, `HSE_STUDIO__JOBS__RELAY_MAX_RESPONSE_BYTES`, `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_PER_USER`, `HSE_STUDIO__JOBS__RELAY_MAX_DURATION_S`, and the memory budget for request bodies held by api: `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_BYTES_PER_USER` (per person), `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_TOTAL` and `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_BYTES_TOTAL` (whole process). Over the budget the chat gets `relay_busy`. A runner that does not answer shows up in the chat as "Runner "…" did not respond" with a way to pick another model.

## Build executors

The runner itself runs signature verification, submission packing, checks and AI relay; office files are converted by a long-running Gotenberg. Only the TeX build needs a separate executor, chosen by `HSE_RUNNER__EXECUTOR`:

| Value | How the build runs | Fits |
|---|---|---|
| `docker` (default) | a sibling TeX Live container through `/var/run/docker.sock` | a machine or VM with Docker, compose |
| `kubernetes` | a separate pod per build in the runner's namespace through the Kubernetes API | a Kubernetes cluster, including containerd nodes without Docker |

The `kubernetes` executor needs no `docker.sock`, no `hostPath` and no privileges: the runner pod and the build pods pass the Pod Security Standard restricted. Sources go into the pod and the result comes back through the Kubernetes API `exec` (a tar stream), so there is no volume shared between the runner and the pods and the build pods need no network. The runner sets CPU and memory limits and `activeDeadlineSeconds` on every pod, deletes the pod when the job is cancelled and removes pods left over from its previous run. The build log goes to the job log as usual.

| Variable | Value |
|---|---|
| `HSE_RUNNER__K8S__NAMESPACE` | namespace of build pods (defaults to the runner's namespace) |
| `HSE_RUNNER__K8S__IMAGE` | TeX image; defaults to `HSE_RUNNER__TEX_IMAGE` |
| `HSE_RUNNER__K8S__CPU_REQUEST`, `…CPU_LIMIT`, `…MEMORY_REQUEST`, `…MEMORY_LIMIT` | build pod resources (500m/2, 1Gi/4Gi) |
| `HSE_RUNNER__K8S__ACTIVE_DEADLINE_S` | pod lifetime limit, seconds (1800) |
| `HSE_RUNNER__K8S__POD_START_TIMEOUT_S` | how long to wait for the pod to start, image pull included (300) |
| `HSE_RUNNER__K8S__NODE_SELECTOR`, `…TOLERATIONS` | build pod placement, JSON |
| `HSE_RUNNER__K8S__RUNTIME_CLASS_NAME` | RuntimeClass for build pods, e.g. `gvisor` |
| `HSE_RUNNER__K8S__TEX_CACHE_CLAIM` | optional PVC with the TeX font cache |

In the Helm chart this is `runner.executor: kubernetes` and the `runner.kubernetes` block (see the chart README): the chart creates the runner ServiceAccount, a Role limited to pods in its namespace (`pods`, `pods/log`, `pods/exec`), a NetworkPolicy that denies build pods any network, and the runner data volume. A build failing with `image_missing` means the node could not pull the TeX image; `build_backend_unavailable` means Kubernetes refused the pod (permissions, quota, no suitable node), details are in the job log. Design and trade-offs: `docs/design/k8s-runner.md`.

## Scaling

Several runners on different machines work together. Two replicas on one machine need different data directories. Besides installation runners there are users' personal runners; organization runners do not exist yet.
