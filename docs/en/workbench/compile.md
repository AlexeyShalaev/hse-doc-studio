---
title: Build and log
description: Building PDFs in a TeX Live container — the queue, the live log, “Explain” and “Fix with AI”.
tags:
  - Workbench
  - Builds
  - LaTeX
---

# Build and log

<p class="hds-lede">A build is latexmk with xelatex in a TeX Live container: as many passes as needed. What you see of it is one button and a live log.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/documents/thesis?tab=compile</span></div>
    <img src="../assets/shots/compile.en.light.png#only-light" alt="Build tab">
    <img src="../assets/shots/compile.en.dark.png#only-dark" alt="Build tab">
  </div>
  <figcaption>the Build tab: the xelatex log, pages and word count</figcaption>
</figure>


## What it does

- **“Build”** — one document; **“Build all”** — the whole set. Builds join a global queue and never choke your laptop.
- **The live log** — real-time status, the page count of the finished PDF, “Cancel”, “Rebuild”, “Download .log”.
- **“Explain”** — the agent reads the log and explains the LaTeX error in plain words, without editing anything.
- **“Fix with AI”** — the agent finds the cause, edits the `.tex` (you confirm every change) and rebuilds.
- **Metadata is stamped in on every build** — change the supervisor once and it changes on the title pages of every document.
- **Text counters** — after a build texcount recounts prose words and characters; visible in the preview.

The first build downloads the TeX Live image (once, a few gigabytes) — see [“First project”](../start/first-project.md). You don't have to untangle LaTeX errors yourself: “Fix with AI” does it for you, showing every diff.


## Queue and concurrency

A runner has a concurrency limit (`concurrency`): how many builds it runs at once. “Build all” queues every document at once, the runner takes as many as the limit allows (a personal runner takes one by default) and the rest honestly wait. So each document has its own state label under the name:

| Label | Meaning |
|---|---|
| “queued”, “queued, position 2” | the job is queued, no runner has taken it yet; waiting is normal |
| “queued, runner busy: 1 of 1” | the suitable runners are fully busy |
| “waiting for your runner” | the build waits for your personal runner, then moves to a shared one |
| “no free runner with the required tags” | no suitable runner is online (offline, wrong tags); not a stall, a runner is needed |
| “building 1:05” | a runner took the build, the time counts from the start of this very build |
| “not responding for 6 min” | the build is running, but it has sent no output line for over 5 minutes |
| “error”, “built” | the result of the last build |

The red “The build is not responding” banner and the red button appear only for a running build that stays silent for more than 5 minutes (the same as the idle time after which a runner drops a build itself, 300 seconds). Time in the queue is not counted; every new output line resets it. While the queue is moving, a calm grey line sits above the document list (“Building: 1, queued: 3”) and the button reads “Cancel queue”.

## Stopping a build

“Stop build” stops both the queue and builds that are already running. For a cloud build the server asks the runner to stop the process and the container, the build record becomes `cancelled`, and the log ends with a `[cancelled]` line. Stopping again is harmless. The author of the build and any member with the right to run builds can stop it.

In the local Studio, while the project is building in the cloud, the button reads “Stop cloud build”: the request goes to the server with the Studio sign-in, the button shows “Stopping…” while it runs, and if it fails (no connection, no right, a new sign-in is needed) the reason is shown in a message. While the cloud has an unfinished build the Studio polls the status every few seconds, so cancel, error and done reach it without a reload; the cloud sees a local build in the list of connected devices.

## When a build fails

A failed build always explains itself: the Build tab shows a banner with the error code and a “what to do” text, and the log below is never empty. The document list shows the reason in red under the document name, and the “Now” block repeats it for each document with an error. The same code and text appear in the cloud and in the local Studio.

Everything available goes into the log: the latexmk output, runner lines (`[runner] …`), the refusal reason (`[error] <code>: <text>`) and the detail (a path, an exception, an address). If there is no output of the build itself, the banner says so: LaTeX was not started (no Docker or image, no runner, quota, disk full) or the runner did not send a single line. A cloud build's log arrives from the runner during the build and is saved in the build record; past the size limit the middle is lost, the beginning and the end stay.

| Code | What happened | What to do |
|---|---|---|
| `build_failed` | LaTeX returned an error | The details hold the first error line; find it in the log (`!` or `file:line:`) and fix the source; “Explain” and “Fix with AI” read the same log. `Running mktextfm Arial` lines in the log are not an error by themselves: that is how XeTeX looks a font up by name, and the template falls back to a free font |
| `font_missing` | The build container lacks a font the document asks for (name in the details) | [Fonts in cloud builds](#fonts-in-cloud-builds) |
| `image_missing` | The machine that builds has no TeX Live image | Settings → Compiler → Images → “Install” on that machine (for a personal runner it is your local Studio) |
| `docker_unavailable` | Docker is not running or `docker.sock` is not accessible | Start Docker Desktop or the daemon; on Linux check the socket group (`DOCKER_GID`) |
| `no_runners`, `no_runner_for_tags` | No live runner takes these documents | Connect a personal runner (a local Studio with Docker) or ask the administrator |
| `quota_exceeded` | The build quota is used up | Wait for the reset or build on a personal runner: it does not spend the quota |
| `timed_out`, `job_timeout` | The build did not finish in time | Check the log for a LaTeX loop; the administrator can raise the build timeout |
| `runner_lost`, `lease_lost`, `runner_shutdown` | The runner disappeared, lost connection or was stopped | Start the runner, check its network and build again |
| `blob_unavailable` | The runner could not fetch the sources | Check that the runner reaches the server and storage addresses (proxy mode for outside runners) |
| `storage_unreachable`, `artifact_upload_failed`, `artifact_invalid` | The PDF is built but was not uploaded to the server | Administrator: the public S3 address (`HSE_STUDIO__S3__PUBLIC_ENDPOINT`) or proxy mode for outside runners, the output size limit |
| `output_*`, `apply_failed` | The server could not accept or place the PDF | Build again; administrator: the api log and free space on the projects volume |
| `pdf_missing` | The build finished but there is no PDF, or the runner lost the built file before the upload | Check that the document produces a PDF; if it repeats, check the runner log |
| `disk_full` | The machine that builds is out of space | Free disk space: runner data, docker images and volumes |
| `build_out_of_memory`, `build_storage_exceeded` | The build pod was killed for memory (OOMKilled) or evicted for exceeding scratch storage | Shrink figures and heavy TikZ; administrator: raise `runner.kubernetes.resources` (memory, ephemeral-storage), see [Runner isolation and limits](../deploy/runner-isolation.md) |
| `staging_failed`, `manifest_*` | The server could not prepare the project (a file too large or unsafe) | Remove large files, rename a file with an unsafe path |
| `cancelled`, `superseded`, `restarted` | The build was cancelled, replaced by a newer one or interrupted by a restart | Build again |

A refusal before the start (no Docker, no image, no runner) is still shown as a dialog with an install button, but it is now also recorded as a failed build of the document: the reason stays in the Build tab and in the list.

### Cloud build on a personal runner and “Build locally”

A cloud build on a personal runner runs on your local Studio: Docker and the image are needed there. The runner sends the log to the server in batches, so the cloud tab shows it live. A build started with “Build” in the local Studio for a project taken from the cloud leaves an ordinary record with the log and the reason; after a successful build the Studio uploads the PDF to the cloud, and the upload result (or the refusal reason) is shown in the same tab.

If a build fails in the cloud but not locally (or the other way round), compare the TeX Live images: the cloud and the personal runner use the image chosen in the Studio settings, while the server's shared runner uses its own.

### Fonts in cloud builds

The GOST templates ask for Times New Roman, Arial and Consolas. The TeX Live image does not contain them (the Microsoft licence does not allow shipping them), so the fonts are attached to the build container separately:

- **Local build and personal runner (your Studio).** Cloud builds use the same fonts folder as local ones (“Settings → Fonts”). If the folder is empty and the computer has Times New Roman, Arial or Consolas, the Studio takes them from the computer once when the runner connects, by the same rules as the first install. If the computer has none either, install them in “Settings → Fonts” and reconnect the runner (switch it off and on under “Settings, Cloud builds”).
- **Shared server runner.** The administrator sets a fonts folder (`HSE_RUNNER__FONTS_DIR`) or a PVC (`HSE_RUNNER__K8S__FONTS_CLAIM`), see [Runners](../deploy/runners.md#fonts-for-builds). Microsoft fonts are not part of the images or the repository: the administrator supplies their own licensed files.
- **Without the fonts** templates with `\IfFontExistsTF` use a free fallback (Tinos for Times New Roman, DejaVu Sans for Arial) and build; only the letter shapes differ a little. If a document asks for a font directly (`\setmainfont{Arial}` with no check), the build fails with the code `font_missing` and the font name. Fix it by providing the font as above, or by replacing it in the preamble with `\IfFontExistsTF{Arial}{\setmainfont{Arial}}{\setmainfont{Liberation Sans}}`.
