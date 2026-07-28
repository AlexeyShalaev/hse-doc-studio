---
title: HSE Doc Studio
description: "A local studio for student documents: theses and course projects to GOST — templates, LaTeX builds, normcontrol and submission packaging. No cloud, no accounts."
hide:
  - navigation
  - toc
render_macros: true
hero:
  eyebrow: "Local · Docker · your files"
  title: "From a blank form — to a signed PDF."
  lede: "HSE Doc Studio builds your thesis or course project end to end: templates for every document, containerised LaTeX builds, GOST normcontrol and submission packaging — on your computer, with no cloud and no accounts."
  actions:
    - text: "Install with one command →"
      href: "start/install/"
      kind: primary
    - text: "First project →"
      href: "start/first-project/"
      kind: ghost
  install: "curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | sh"
  install_ps: "irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex"
  fine: "Apache-2.0 · linux/amd64 and arm64 · the only requirement is a running Docker."
  sheet:
    title: "Submission package · Thesis"
    stamp: "Checked · normcontrol"
    items:
      - { code: "TS", tone: "st1", name: "Technical specification", done: true }
      - { code: "ExN", tone: "st2", name: "Explanatory note", done: true }
      - { code: "TPr", tone: "st3", name: "Test program", done: true }
      - { code: "PG", tone: "st4", name: "Programmer's guide", done: true }
      - { code: "Slides", tone: "stsub", name: "Defence slides", done: false }
      - { code: "Thesis", tone: "st5", name: "Thesis text", done: false }
---

# HSE Doc Studio { .hds-visually-hidden }

<p class="hds-eyebrow" style="text-align:center; margin-top:2.5rem">What the template pack already covers</p>

{{ pack_stats_strip('en') }}

<div class="hds-reel hds-wide">
  <video class="hds-only-light" src="assets/reel/reel.en.light.mp4" poster="assets/reel/reel-poster.en.light.png" autoplay muted loop playsinline></video>
  <video class="hds-only-dark" src="assets/reel/reel.en.dark.mp4" poster="assets/reel/reel-poster.en.dark.png" autoplay muted loop playsinline></video>
</div>

## Source on the left. What they will accept on the right.

<p class="hds-lede">Side-by-side mode: the visual editor and the built PDF on one screen. Ctrl+click works both ways — from the PDF to the source line and back.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar">
      <span class="hds-shot__brand">HSE DOC STUDIO</span>
      <span class="hds-shot__route">/projects/vkr/documents/thesis</span>
    </div>
    <img src="assets/shots/workspace.en.light.png#only-light" alt="Side-by-side mode: PDF and the visual editor">
    <img src="assets/shots/workspace.en.dark.png#only-dark" alt="Side-by-side mode: PDF and the visual editor">
  </div>
  <figcaption>Side-by-side mode: PDF preview and the visual editor next to each other</figcaption>
</figure>

- **<span class="hds-fill">\hseFill</span> fields are highlighted** — ++tab++ jumps to the next unfilled one.
- **“GOST margins”** — 30/15/20/20 mm guides drawn right over the PDF page.
- **Word and page counters** — refreshed on every build.

## One project. One set of metadata. Every document.

<p class="hds-lede">Change your supervisor's academic title once in the settings — at the next build it changes on every title page at once. The specification, test programme, manuals, slides and the thesis itself build from one project; the course project and the Project Proposal work the same way, from their own templates.</p>

<p style="text-align:center"><a href="reference/pack/">How packs, templates and documents work →</a></p>

## Findings land in the margins, not in your inbox.

<p class="hds-lede">Checks run against what actually built — the finished PDF and the build log, not guesses from the source.</p>

<div class="hds-finding hds-finding--err">
  <div class="hds-finding__rule">gost-7.32-2017/page-margins</div>
  <div class="hds-finding__msg">Left margin is 25 mm, 30 mm required.</div>
  <div class="hds-finding__loc">thesis/thesis.tex · page 1</div>
</div>
<div class="hds-finding hds-finding--warn">
  <div class="hds-finding__rule">gost-19.201-78/section-stages</div>
  <div class="hds-finding__msg">The technical specification is missing the “Development stages” section.</div>
  <div class="hds-finding__loc">whole document</div>
</div>
<div class="hds-finding hds-finding--info">
  <div class="hds-finding__rule">typography-ru/quotes</div>
  <div class="hds-finding__msg">Straight quotes "…" instead of guillemets «…».</div>
  <div class="hds-finding__loc">thesis/thesis.tex · line 214</div>
</div>

The rules come from the ESPD GOST family and GOST 7.32-2017, Russian typography and LanguageTool. [How normcontrol works →](reference/checks-rules.md)

## An assistant that reads your build log instead of guessing.

<p class="hds-lede">Hit “Fix with AI” on a failed build: the agent reads the log, edits the <code>.tex</code> and rebuilds. Every write to disk is confirmed by you.</p>

Bring your provider — Anthropic, OpenAI, any OpenAI-compatible API, or local Ollama: with a local model your thesis never leaves the machine. [More about the agent →](workbench/agent.md)

## Everything stays local

<div class="hds-wide" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(16rem,1fr)); gap:2rem; margin-top:1.5rem">
  <div>
    <h4 style="margin:0">Your files are yours</h4>
    <p style="font-size:.9rem">A project is a plain folder of <code>.tex</code> files on your disk. Edit it in VS Code — the Studio notices and offers a diff.</p>
  </div>
  <div>
    <h4 style="margin:0">No database, no cloud, no account</h4>
    <p style="font-size:.9rem">All state is files in a folder you choose — back it up and you have backed up everything. <a href="reference/privacy/">What goes over the network →</a></p>
  </div>
  <div>
    <h4 style="margin:0">History, just in case</h4>
    <p style="font-size:.9rem">Every edit and build lands in a dedicated git inside <code>.hse-studio/git/</code>. Rolling back to “chapter 3 that still worked” is one button.</p>
  </div>
</div>

## One command. Then the app asks where to keep your work.

<p class="hds-lede">The script checks that Docker responds, pulls the image and opens your browser; running it again breaks nothing.</p>

=== "Script (macOS / Linux)"

    ```sh
    --8<-- "install-sh.txt"
    ```

=== "PowerShell (Windows)"

    ```powershell
    --8<-- "install-ps1.txt"
    ```

=== "Docker Compose"

    ```sh
    --8<-- "install-compose.txt"
    ```

Every flag explained, Compose overlays and the manual `docker run` — in [Installation](start/install.md).

## Ready to start?

<div style="display:flex; flex-wrap:wrap; gap:.8rem; justify-content:center; margin:1.5rem 0 2rem">
  <a class="hds-btn" href="start/install/">Install →</a>
  <a class="hds-btn hds-btn--ghost" href="start/first-project/">First project</a>
</div>
