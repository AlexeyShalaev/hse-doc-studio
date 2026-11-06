---
title: AI model servers
description: Install Ollama, vLLM and SGLang from the admin console next to the Studio, estimate requirements, register the AI provider automatically.
tags:
  - Deployment
  - Administration
  - AI
---

# AI model servers

<p class="hds-lede">The admin console (`/admin`, "Model servers") installs a model server, runs it in a sibling Docker container and registers a shared AI provider that everyone can use.</p>

The page is available to the instance administrator only, in shared-server mode. For now the `/api/admin/model-servers` API is available; the admin page comes in a following step.

## Engines

| Engine | Use it for | GPU needed |
|---|---|---|
| Ollama | the easiest start, models from the ollama.com library | no, slower on CPU |
| vLLM | fast OpenAI-compatible server, Hugging Face models | yes, NVIDIA |
| SGLang | the same for an OpenAI-compatible API, Hugging Face models | yes, NVIDIA |

From the hardware probe the page shows the GPU and its memory, RAM, cores, architecture and free disk. An engine that lacks a GPU is marked with the reason and is not installed (the API answers `409 model_server_engine_requires_gpu`).

## Estimate before downloading

For the chosen model the Studio computes the memory and disk needed from the parameter count and quantization and compares them with the hardware: fits, tight, too large, size unknown. The estimate is approximate: real usage depends on the context length and concurrent requests. A model that clearly will not fit is not installed without an explicit confirmation.

Pick a model from the short catalog or type a name: an Ollama library tag (`qwen3:8b`) or a Hugging Face id (`Qwen/Qwen3-8B`).

## What an install does

1. Starts the engine container (the image is configurable, the official one by default). With an NVIDIA card and the NVIDIA Container Toolkit the container gets the GPU. Ollama falls back to CPU if the GPU is refused; vLLM and SGLang do not.
2. Waits for the engine. For Ollama the model is downloaded and progress is shown per step. vLLM and SGLang download weights at startup, so "ready" comes later and the container log shows the progress.
3. Creates a shared AI provider (Ollama type for Ollama, OpenAI-compatible for vLLM and SGLang) pointing at the container's `/v1` with the model.
4. The "model responds" check: a short completion request. If the model is still loading into memory the step is marked as a warning, and the server and provider stay.

One install runs at a time (`HSE_STUDIO__MODEL_SERVERS__MAX_CONCURRENT_INSTALLS`). Progress and the step log live in process memory and disappear on restart; the servers themselves stay and are found by container labels.

A server can then be stopped, started, inspected through the container log and removed. Removal also deletes the provider. Model volumes stay by default; "also delete downloaded models" clears the engine volume unless other servers of that engine share it.

## Security

- The container is not published: in the shared Docker network only the Studio sees it, without the network the port is open on the host's `127.0.0.1` only.
- vLLM and SGLang run with an API key. The key is generated (32 bytes), stored encrypted as the shared provider's key, and never appears in API responses or the audit log.
- Container secrets (API key, Hugging Face token) are passed through a temporary `0600` file that is deleted right after the start, not through process arguments.
- `model_server.install`, `.start`, `.stop`, `.remove` go to the audit log: engine, model, target, no secrets.
- The install needs the Studio to reach the host `docker.sock`. The socket equals root on the host: give it only to an installation you trust.

## Kubernetes

**Installing next to the Studio is not supported in Kubernetes.** It is off in the Helm chart: `modelServers.local.enabled: false` (`HSE_STUDIO__MODEL_SERVERS__LOCAL_ENABLED=false`). The reason: the install starts sibling containers through the node's docker.sock, which the api pod does not get (the socket equals root on the node and breaks Pod Security restricted, so the chart does not mount it). The page hides the "on this machine" option and the API answers `409 model_server_local_install_disabled`. You can turn it on only by editing the chart by hand (a hostPath mount of the socket into the api pod on a dedicated node), at your own risk. For a cluster use an install on a separate machine over SSH, or an external model server added as an ordinary AI provider.

## Settings

| Variable | Purpose |
|---|---|
| `HSE_STUDIO__MODEL_SERVERS__LOCAL_ENABLED` | allow installing next to the Studio (yes by default, off in Helm) |
| `HSE_STUDIO__MODEL_SERVERS__OLLAMA_IMAGE`, `..._VLLM_IMAGE`, `..._SGLANG_IMAGE` | engine images; empty means the default image with a pinned tag (Ollama 0.40.15, vLLM v0.32.0, SGLang v0.5.23) |
| `HSE_STUDIO__MODEL_SERVERS__MAX_CONCURRENT_INSTALLS` | number of concurrent installs |
| `HSE_STUDIO__MODEL_SERVERS__STARTUP_TIMEOUT_S`, `..._READY_TIMEOUT_S` | how long to wait for start and readiness (vLLM and SGLang on the first weight download) |
