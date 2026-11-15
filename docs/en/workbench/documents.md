---
title: Documents
description: The project's document panel — the “Now” block, statuses, “Build all” and the single-document screen.
tags:
  - Workbench
  - Documents
---

# Documents

<p class="hds-lede">The Documents panel is the project's main worklist: every document of the set, its status, and the “Now” block that answers “what is blocking my submission”.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/documents/thesis</span></div>
    <img src="../assets/shots/documents.en.light.png#only-light" alt="Documents panel">
    <img src="../assets/shots/documents.en.dark.png#only-dark" alt="Documents panel">
  </div>
  <figcaption>the Documents panel: the set, statuses and the PDF preview</figcaption>
</figure>


## What it does

- **“Now”** — the top blockers (“build error”, “form not filled in”, “signature missing”); a click takes you straight to the problem.
- **Statuses** — “Not built”, “Ready”, “With findings”, “Check errors” (the PDF is built), “Build error”; a filter and counter chips, plus author chips in team projects.
- **“Build all”** — the whole set with one button; “Stop” while a build is running.
- **The document screen** — a “Build” button, the Preview / Editor / Side-by-side views and the Findings · Build · Log · Signatures pages.
- **“Replace with my own file…”** — your own PDF/DOCX instead of the generated one (e.g. a scan of a signed assignment); “Revert to template” brings it back.
- **“Open in editor”** — jump to the file in an installed VS Code or Cursor.

## Files under the hood

Every document is plain `.tex` files in the project folder; the full tree lives in the Files mode on the rail. The folder layout is in the [reference](../reference/layout.md).

Your own files (PNG, JPG and SVG images, figures and scans in PDF, `.bib`, `.tex` and anything else) are uploaded in Files: with "Upload files" or "Upload folder" in the tree header, with "Upload files here" in a folder menu, or by dragging them from your computer onto a folder or empty space in the tree. If the name is taken, the Studio asks: replace, keep both or skip. One file is at most `HSE_STUDIO__SERVER__PROJECT_FILE_MAX_BYTES` (50 MB by default, below the roughly 100 MB limit of git hosting services), and on a server the project space limit applies too. Uploaded files, including a PDF without a same-named source next to it, go into the version history and the git sync; built document PDFs stay out of history unless "Keep built PDFs in history" is on.
