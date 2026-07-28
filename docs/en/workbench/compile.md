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
