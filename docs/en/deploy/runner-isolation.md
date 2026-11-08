---
title: Runner isolation and limits
description: CPU, memory and storage limits of runners in Kubernetes, network isolation, pod security, quota, and how to verify it on a cluster.
tags:
  - Deployment
  - Runner
  - Security
---

# Runner isolation and limits

<p class="hds-lede">Build pods run the TeX code of user documents, so in Kubernetes they get hard limits, no network and a restricted pod. This page lists what the Helm chart sets, which knobs exist and how to check it.</p>

## Resource limits

| Pod | Defaults (requests / limits) | Where to change |
|---|---|---|
| runner (chart runner, `executor: docker` or `kubernetes`) | cpu 100m / 1, memory 256Mi / 2Gi, ephemeral-storage 128Mi / 2Gi | `runner.resources`, `runner.tmpSizeLimit` |
| build pod (`executor: kubernetes`) | cpu 500m / 2, memory 1Gi / 4Gi, ephemeral-storage 1Gi / 4Gi | `runner.kubernetes.resources` |
| runner installed from the admin area | same as the chart runner | `runner.installFromUi.resources`, or the install form |
| build pod of a runner installed from the admin area | cpu 500m / 2, memory 1Gi / 4Gi | `runner.installFromUi.buildResources`, or the install form |

Why 4Gi of memory for a build: XeLaTeX on an ordinary document (a GOST template, tens of pages, figures) takes about 0.5 to 1.5 GiB; large TikZ plots and high-resolution images can take up to 3 GiB. The limit leaves headroom; the request (1Gi) is what the scheduler reserves. Ephemeral storage covers `/work` (`workSizeLimit`, 2Gi), `/tmp` (`tmpSizeLimit`, 1Gi) and logs, so keep `ephemeral-storage` limit at least their sum.

### The install form (Kubernetes)

In "Install a runner" the "Resource limits" block takes four optional limits: runner CPU and memory, build pod CPU and memory. Empty means the Helm default. Requests follow the limit (the default request, or the limit if it is smaller). The backend checks the values before it issues a token or creates anything:

- format: Kubernetes quantities (`500m`, `2`, `512Mi`, `4Gi`);
- lower bounds: runner 100m and 256Mi, build pod 500m and 1Gi (below that TeX is killed on ordinary documents);
- upper bounds: `runner.installFromUi.maxCpu` (8) and `maxMemory` (16Gi).

A violation is answered with 422 `invalid_resources` (field name and reason `format`, `min` or `max` in the detail). The chosen limits are written to the audit log (`runner_install.local.start`). Runners installed earlier keep what they have until they are installed again; Update from the admin area carries them into the new manifest; their build pods take the new ephemeral-storage limit from the runner image.

### When a build is killed

A build pod killed for memory (`OOMKilled`, or latexmk killed by SIGKILL inside a live pod) fails with the code `build_out_of_memory`; a pod evicted for exceeding ephemeral storage fails with `build_storage_exceeded`. The user sees a text with the usual causes (huge figures, TikZ with too many points, macro recursion) and what to do, the administrator sees the limit in the detail line. This is not `build_failed` and not `build_backend_unavailable`. If ordinary documents hit it, raise `runner.kubernetes.resources.limits.memory`.

## Network

| What | Policy |
|---|---|
| Build pods (chart runner with `executor: kubernetes`, and runners installed from the admin area) | no ingress, no egress at all: sources and results travel through the Kubernetes API `exec`, so a build pod cannot reach other pods, the database, the cloud metadata service or the internet. The policy lives in the build pods namespace: `runner.kubernetes.namespace` for the chart runner, `runner.installFromUi.buildNamespace` for runners from the admin area (empty means the release namespace). Switch: `runner.kubernetes.networkPolicy.enabled` (on by default) |
| Runner pods | optional `runner.networkPolicy.enabled` (off by default): egress only to DNS (port 53), the Studio api of the release (port 8000), the Kubernetes API (`apiServerPorts`, default 443 and 6443), the built-in Gotenberg (port 3000, when `services.officeConvert` is on) and `extraEgress` |
| Built-in Gotenberg (`services.officeConvert`) | ingress only from the release runner pods (the chart runner and runners from the admin area) on port 3000, egress closed entirely. Switch: `services.officeConvert.networkPolicy.enabled` (on by default). More in [runners](runners.md#office-jobs-in-the-cluster-gotenberg) |

Policies need a CNI that enforces NetworkPolicy (Calico, Cilium, and so on); without one they are silently ignored. The build pod policy is on by default because it cannot break anything: those pods need no network. The runner policy is off by default because the chart cannot know two addresses a runner needs: the Kubernetes API server and, when the object storage is outside the cluster or has an internal address that is not a pod of the release, the S3 endpoint (a runner fetches sources and uploads results by presigned links). A wrong list would cut running runners off.

Turning the runner policy on:

1. Find the API server address: `kubectl get endpoints kubernetes -o wide`. Put it into `runner.networkPolicy.apiServerCidrs` (for example `["10.0.0.5/32"]`) and the port into `apiServerPorts`. Left empty, the policy opens the listed ports to any address except `169.254.0.0/16` (the cloud metadata service).
2. Add the storage to `runner.networkPolicy.extraEgress`, verbatim `spec.egress` entries, for example an `ipBlock` and port 443 for external S3, or a `namespaceSelector` and `podSelector` for MinIO in the cluster. With `s3.outsideRunnerAccess: proxy` runners send results to the api and need no S3 rule.
3. Add rules for what the runner uses besides that: an external Gotenberg (`runner.officeUrl`), AI endpoints for the relay. The policy allows the built-in Gotenberg (`services.officeConvert`) by itself.

If the cluster has a default-deny ingress policy in the release namespace, allow ingress to the api from runner pods yourself.

## Pod security

Build pods and chart runners pass the Pod Security Standard restricted:

- `runAsNonRoot`, uid and gid 1000, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true` (writes go to the bounded `emptyDir` volumes `/work` and `/tmp`);
- no `privileged`, no `hostPath`, no host network and PID (the docker executor is the exception: it needs `docker.sock`, which equals root on the node; use dedicated nodes);
- `automountServiceAccountToken: false` on build pods, the api (unless install from the admin area is on), the migration job and the docker runner; the Kubernetes runners keep the token because they create build pods, with a Role limited to pods in one namespace;
- `enableServiceLinks: false`, `activeDeadlineSeconds` (1800) on build pods, `ephemeral-storage` requests and limits everywhere.

The built-in Gotenberg pod (`services.officeConvert`) passes restricted too: the image uid 1001, a read-only root, `/tmp` and `/home/gotenberg` on `emptyDir`, no ServiceAccount token.

Label the namespaces with `pod-security.kubernetes.io/enforce=restricted`: the chart cannot label the release namespace, and the check also stops anything the Studio might create there by mistake.

### Permissions of the Studio ServiceAccount

With `runner.installFromUi.enabled` the Studio gets one namespaced Role: Deployments (`create`, `list`, `delete`; the list is by label to show installed runners), Secrets (`create`, `delete`, no reading), PersistentVolumeClaims (`create`, `delete`). There is no `get` and no `update` on anything, no Roles, RoleBindings, ServiceAccounts, pods or `pods/exec`, and no ClusterRole. The Studio picks the runner ServiceAccount of the chart by a fixed name, whose Role covers build pods only. Remaining risk: whoever can create Deployments in the namespace can run any image there, so enforce restricted pod security on the namespace and keep the installFromUi switch off where shared runners are not wanted.

## Quota and LimitRange (option)

For a separate build namespace (`runner.kubernetes.namespace` for the chart runner, `runner.installFromUi.buildNamespace` for runners from the admin area) the chart can add a ResourceQuota (`runner.kubernetes.quota`: pods, total requests and limits of CPU, memory and ephemeral storage) and a LimitRange (`runner.kubernetes.limitRange`: container defaults and a maximum). Both are off by default. Build pods set their own requests and limits, so they satisfy the quota; the LimitRange protects against foreign pods in that namespace. When a quota is full, the pod is refused and the build fails with `build_backend_unavailable` and the Kubernetes reason in the detail. The chart refuses to render a quota in the release namespace (it would limit the Studio too). The quota and LimitRange values are shared by both kinds of runners: a shared namespace gets one object and one ceiling, different namespaces get one object each with these values. Runners installed from the admin area without `buildNamespace` create build pods in the release namespace, so a quota does not apply to them; moving them to their own namespace is described in [runners](runners.md#a-separate-build-pods-namespace).

## What the admin area shows

"Runners and queue" has two places with technical information. Each value is labelled with its source and the screen never mixes them: "configured" comes from configuration, "reported by the runner" from the runner's own report, "checked in the cluster" from the Kubernetes API.

**Runner details** (row menu, "Deployment details"):

- executor (`docker` or `kubernetes`), where the runner itself runs (pod, container, host), the runner version next to the Studio version and an "outdated" mark;
- the hint "reinstall the runner or upgrade the Helm release so the limits apply" when the runner is older than 0.14.0 or its pod has no CPU and memory limits. The same mark sits next to the version in the table;
- namespace and pod name, ServiceAccount, CPU, memory and ephemeral storage requests and limits of the runner itself (from the pod downward API; with older manifests only the cgroup limits);
- build pods: namespace, TeX image, requests and limits, `/work` and `/tmp`, `activeDeadlineSeconds`, RuntimeClass, and for the docker executor no network and the process limit;
- securityContext: `runAsNonRoot` and uid, read-only root, no privilege escalation, seccomp, dropped capabilities, ServiceAccount token. For the runner these are observed on its own process (`/proc/self/status`), for build pods it is what the runner writes into the manifest;
- for a runner installed from the admin area, its Deployment from the cluster: image, readiness, requests and limits, build pod limits and securityContext. The Studio reads it with the `list` right it already has for installing.

The runner reports this itself after `/announce` (protocol feature `deployment_info`, `POST /api/runner/v1/deployment`) and repeats hourly. Older runners cannot, their details say "no data"; older servers do not negotiate the feature, so a new runner sends them nothing. Personal runners' reports are not stored and not shown. The report carries no tokens, environment variables or addresses.

**"Runner isolation in the cluster"** below the runner list:

- the chart runner (executor, replicas, namespace, ServiceAccount, data volume, requests and limits, securityContext, a `docker.sock` warning, the Gotenberg address for office jobs or "no"), build pods, defaults and bounds of the install form and the Gotenberg address such runners get;
- network: deny-all for build pods (chart runner and runners from the admin area), the runner egress policy and what it allows (DNS, Studio api port, API server addresses and ports, the built-in Gotenberg, number of `extraEgress` rules);
- the built-in Gotenberg when it is on: address, image, replicas, requests and limits, network policy;
- ResourceQuota and LimitRange of the build namespace and, when runners from the admin area have their own build pods namespace, its ResourceQuota and LimitRange separately; Pod Security labels of the release namespace and every build namespace.

What the chart configures is always known: the chart puts a summary of the values into `HSE_STUDIO__RUNNER_CLUSTER__DECLARED` (no secrets). That is not a check, so the screen says "configured" and "not checked in the cluster". To let the Studio compare it with the cluster, set `runner.isolationInfo.readCluster: true`. The chart then gives the Studio ServiceAccount a Role with `get` and `list` on NetworkPolicy, ResourceQuota and LimitRange in the release namespace and the build pods namespaces (`runner.kubernetes.namespace` and `runner.installFromUi.buildNamespace`), and a ClusterRole with `get` on those namespaces only (by `resourceNames`, for the Pod Security labels). No Secrets, no pods, no writes. When some of these rights are missing the screen says "partly checked" and never presents unchecked values as checked. Outside Helm (docker compose) the block shows only the install-from-admin settings.

## Checking on a cluster

```sh
# 1. Rendering and defaults
helm template rel deploy/helm/hse-doc-studio -f my-values.yaml | grep -A12 'kind: NetworkPolicy'

# 2. A build pod has limits and a restricted context (run a build, then within 1800 s)
kubectl -n <builds-ns> get pod -l hse-doc-studio/component=build -o jsonpath='{.items[0].spec.containers[0].resources}'
kubectl -n <builds-ns> auth can-i --as=system:serviceaccount:<ns>:<runner-sa> get secrets   # no

# 3. A build pod has no network (needs a CNI that enforces NetworkPolicy); both connects must fail
kubectl -n <builds-ns> exec <build-pod> -c tex -- sh -c 'timeout 3 bash -c "echo > /dev/tcp/169.254.169.254/80"; echo rc=$?'   # rc != 0
kubectl -n <builds-ns> exec <build-pod> -c tex -- sh -c 'timeout 3 bash -c "echo > /dev/tcp/<api-pod-ip>/8000"; echo rc=$?'   # rc != 0

# 4. The Studio permissions
kubectl auth can-i --as=system:serviceaccount:<ns>:<release>-api create deployments -n <ns>        # yes
kubectl auth can-i --as=system:serviceaccount:<ns>:<release>-api get secrets -n <ns>               # no
kubectl auth can-i --as=system:serviceaccount:<ns>:<release>-api create roles -n <ns>              # no

# 5. Memory limit: a document with a deliberately huge figure ends with build_out_of_memory
kubectl -n <builds-ns> get events --field-selector reason=OOMKilling
```

The kind job in CI (`k8s-runner-kind`) runs build pods under restricted pod security on a real cluster; the NetworkPolicy, the runner egress policy and the quota are checked in CI only by rendering (`helm template` golden files and unit tests), so verify them on your cluster with the commands above.
