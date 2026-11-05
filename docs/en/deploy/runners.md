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

## When there are no runners

On a server, documents are built only on runners. The interface learns in advance which tags (`tex`, `office`) have a live runner right now, shared or the project owner's personal one, and refreshes this by itself without a page reload (`GET /api/v1/projects/{id}/build-availability`).

- No runner at all: Build, Build all and rebuild are disabled, with an explanation next to them. The document can be built locally in the desktop Studio (the project syncs, and the finished PDF is uploaded to the server), or the administrator can connect a runner; administrators get a link to Runners.
- Runners exist but without the needed tag (for example, no runner with `office`): only those documents are blocked, Build all builds the rest.
- If a runner disappears between the check and the click, the server answers 409 with code `no_runners` or `no_runner_for_tags` and a `tags` list, and the interface shows a single message.

Local mode needs no runners and never blocks the build.

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

Declaring an endpoint is not enough: the cloud does not create a provider by itself. The person adds a "Through my runner" provider in the cloud once (or clicks "Add in the cloud" in the connected Studios panel), and only then does the model appear in the chat picker. The server works out the state of every endpoint itself and shows it in the Studio panel and in "My Studios": provider not added, nothing opened, runner not paired, offline, paused, revoked or personal runners switched off, the model on the machine does not answer, no models. More: [Local version from the cloud](../start/local-from-cloud.md). When the model behind a runner does not answer, the chat says so directly ("the model on its computer does not answer", "Runner is offline"), and an overflowing Ollama window (4096 tokens by default) is explained with the numbers and a hint to raise `num_ctx`.

api-side limits: `HSE_STUDIO__JOBS__RELAY_PICKUP_S` (how long to wait for the runner to take the request), `HSE_STUDIO__JOBS__RELAY_MAX_REQUEST_BYTES`, `HSE_STUDIO__JOBS__RELAY_MAX_RESPONSE_BYTES`, `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_PER_USER`, `HSE_STUDIO__JOBS__RELAY_MAX_DURATION_S`, and the memory budget for request bodies held by api: `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_BYTES_PER_USER` (per person), `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_TOTAL` and `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_BYTES_TOTAL` (whole process). Over the budget the chat gets `relay_busy`. A runner that does not answer shows up in the chat as "Runner "…" did not respond" with a way to pick another model.

## Runners outside the server network

A runner sends a build result to object storage (S3) through a presigned link issued by the api; project sources it fetches from the api itself. Whoever receives the link opens it, so the address must be routable from that machine. The internal S3 address (`http://minio.<namespace>.svc`, `http://minio:9000`) is visible only inside the server network.

| Who | What it does | S3 address |
|---|---|---|
| api | every storage operation | internal, `HSE_STUDIO__S3__ENDPOINT` |
| shared runner inside the server network (pod in the cluster, compose container) | uploads a result by link | internal |
| personal runner, local Studio, runner on another machine | uploads a result by link | public, `HSE_STUDIO__S3__PUBLIC_ENDPOINT` |
| browser | build and submission PDF by link (redirect from the api) | public |

The S3 (v4) request signature includes the host, so a link is signed for the address it will be opened at. Rewriting the host in a finished link does not work: the storage answers 403. Without `PUBLIC_ENDPOINT`, outside recipients get the internal address (as before this setting). A build on a personal runner then fails with `storage_unreachable` and the text "object storage at ... is not reachable from this machine" naming the settings, and the Self-diagnostics page in the admin area warns: "N runner(s) outside the server network, but the storage has no public address".

### Publishing the storage

1. Expose only the S3 API (MinIO port 9000) under a dedicated name, for example `files.example.org`, with TLS. Do not publish the MinIO console (9001) or metrics (`/minio/v2/metrics`). The name must lead to the storage root: an address with a path prefix is not supported.
2. The proxy must pass the `Host` header unchanged: the storage verifies the signature against it.
3. Set the address: `s3.publicEndpoint` in Helm, `S3_PUBLIC_ENDPOINT` in the compose `.env`, or `HSE_STUDIO__S3__PUBLIC_ENDPOINT`. The value is scheme, host and port without a path: `https://files.example.org`.
4. Restart the api and open Self-diagnostics: the storage warning should disappear.

Kubernetes, Ingress (ingress-nginx; substitute your host, service name and namespace):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: studio-s3
  namespace: <namespace-minio>
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "0"
    nginx.ingress.kubernetes.io/proxy-request-buffering: "off"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      limit_except GET HEAD PUT { deny all; }
spec:
  ingressClassName: nginx
  tls:
    - hosts: [files.example.org]
      secretName: files-tls
  rules:
    - host: files.example.org
      http:
        paths:
          - path: /<bucket>/
            pathType: Prefix
            backend:
              service:
                name: <minio-service>
                port: {number: 9000}
```

The `configuration-snippet` annotation is disabled by default in recent ingress-nginx versions (`allow-snippet-annotations`): if it is off, restrict the methods in the controller policy or use the Gateway API.

Kubernetes, Gateway API (`HTTPRoute` attached to an existing Gateway with an HTTPS listener for that name):

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: studio-s3
  namespace: <namespace-minio>
spec:
  parentRefs:
    - name: <gateway>
      namespace: <namespace-gateway>
  hostnames: [files.example.org]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /<bucket>/}
          method: GET
        - path: {type: PathPrefix, value: /<bucket>/}
          method: HEAD
        - path: {type: PathPrefix, value: /<bucket>/}
          method: PUT
      backendRefs:
        - name: <minio-service>
          port: 9000
```

If the Gateway and MinIO are in different namespaces, add a `ReferenceGrant`. Compose: a reverse proxy on the host (nginx, Caddy) with TLS in front of MinIO port 9000; the port is not published in `docker-compose.yml`, so attach the proxy to the compose network or publish the port on `127.0.0.1` with an overlay.

### Security

- The bucket stays private. There is no anonymous access: an object can be opened only through a link signed with the api keys, only with the method and for the key it was issued for. A read link does not work for writing.
- S3 access keys are never handed to runners or browsers. A runner gets a write link for one output of its own job (prefix `artifacts/<project>/jobs/<job>/`); the api verifies size and sha256 on completion.
- Link lifetime: 15 minutes for a result upload, 2 minutes for a PDF download. The signature is in the URL, so TLS on the public name is mandatory and the proxy must not log the query string.
- Outside, `GET`, `HEAD` and `PUT` on the bucket paths are enough. Block `DELETE`, `POST`, listing and other buckets at the proxy, as in the examples above.
- CORS is needed only by the browser (pdf.js reads the PDF by link with a `Range` header from another origin), not by runners. MinIO answers CORS for any origin by default; narrow it to the Studio address with the MinIO setting `MINIO_API_CORS_ALLOW_ORIGIN`. For AWS, Yandex Object Storage and Ceph set `HSE_STUDIO__S3__CORS_ORIGINS=["https://studio.example.org"]` (Helm `s3.corsOrigins`): the api applies the bucket CORS on startup.

### When the storage cannot be published

`HSE_STUDIO__S3__OUTSIDE_RUNNER_ACCESS=proxy` (Helm `s3.outsideRunnerAccess: proxy`, compose `S3_OUTSIDE_RUNNER_ACCESS=proxy`) turns links off for runners outside the network: they send the result to the api itself (`PUT /api/runner/v1/jobs/{id}/artifacts/{sha256}`) and the api stores it. The runner and job tokens are checked, the size cannot exceed the announced one, the announced one cannot exceed `HSE_STUDIO__JOBS__MAX_ARTIFACT_BYTES` (512 MiB), and the sha256 is verified before anything reaches the storage.

The cost: all result traffic of such runners goes through the api. The body is received into a temporary file (up to 8 MiB in memory, the rest on disk), so the api disk needs room for the number of concurrent uploads times the result size, and the ingress in front of the api must pass large bodies (for ingress-nginx `proxy-body-size`) and not cut long requests. For the browser nothing changes: a PDF by link still needs the public address.

A shared runner located outside the server network (another VM) counts as internal. Declare it outside: `HSE_STUDIO__S3__SHARED_RUNNERS_OUTSIDE=true` (Helm `s3.sharedRunnersOutside`). Design and decisions: `docs/design/s3-public-endpoint.md`.

## Connected Studios and presence

Once a minute a local Studio sends the server a presence signal over its device-code sign-in: the computer name, the version, what it is doing, the runner and model state, and the sync of cloud projects. The server keeps the fresh time in memory and writes a database row when the state changed or once every two minutes; "online" means a signal not older than three minutes. A device is forgotten after 60 days of silence and a person has at most 20 devices. The intervals are `HSE_STUDIO__DEVICES__INTERVAL_S`, `ONLINE_WINDOW_S`, `PERSIST_INTERVAL_S` and `RETENTION_DAYS` ([reference](env-reference.md)). A person sees their own devices in full, other project members only "working locally", and an instance administrator sees as much as any person. Decisions: `docs/design/connected-devices.md`.

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
| `HSE_RUNNER__K8S__FONTS_CLAIM` | optional PVC with fonts (`.ttf`, `.otf`, `.ttc`), mounted read-only into the build pods |

In the Helm chart this is `runner.executor: kubernetes` and the `runner.kubernetes` block (see the chart README): the chart creates the runner ServiceAccount, a Role limited to pods in its namespace (`pods`, `pods/log`, `pods/exec`), a NetworkPolicy that denies build pods any network, and the runner data volume. A build failing with `image_missing` means the node could not pull the TeX image; `build_backend_unavailable` means Kubernetes refused the pod (permissions, quota, no suitable node), details are in the job log. Design and trade-offs: `docs/design/k8s-runner.md`.

## Scaling

Several runners on different machines work together. Two replicas on one machine need different data directories. Besides installation runners there are users' personal runners; organization runners do not exist yet.
