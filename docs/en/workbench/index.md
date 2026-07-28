---
title: Workbench overview
description: The project workspace — the mode rail, one swappable panel, the canvas and the command palette.
tags:
  - Workbench
---

# Workbench overview

<p class="hds-lede">An open project is the Workbench: a narrow mode rail on the left, one swappable panel next to it, and the canvas with the document in the centre. The layout is familiar to anyone who has seen VS Code.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/documents/thesis</span></div>
    <img src="../assets/shots/workspace.en.light.png#only-light" alt="Workbench: Side-by-side">
    <img src="../assets/shots/workspace.en.dark.png#only-dark" alt="Workbench: Side-by-side">
  </div>
  <figcaption>the workbench: PDF preview and the visual editor side by side</figcaption>
</figure>


## What is on screen

- **The mode rail** — Documents, Findings, Submission, Files, Settings, History, Agent; badges show errors, blockers and build progress.
- **The panel** — the contents of the selected mode; **the canvas** — the document: preview, editor or Side-by-side mode.
- **The title bar** — the project switcher (++ctrl+p++), the agent button, settings, the version.
- **The status bar** — Docker state, the LaTeX engine and a reminder about ++ctrl+k++.
- **The command palette** ++ctrl+k++ — new project, theme switching, the agent, jumps to preview/findings/log, opening any project.
- **Team projects** — author chips and shared documents in the panel; Submission assembles one author's package at a time.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| ++ctrl+k++ | Command palette |
| ++ctrl+b++ | Toggle the panel |
| ++ctrl+j++ | Agent dock |
| ++ctrl+p++ | Project switcher |
| ++ctrl+n++ | New project |
| ++ctrl+comma++ | Settings |
| ++ctrl+shift+e++ | Documents |
| ++ctrl+shift+m++ | Findings |
| ++ctrl+shift+f++ | Files |
| ++ctrl+shift+d++ | Submission |
| ++ctrl+shift+b++ | Build all |
| ++slash++ | Focus the panel filter |

On macOS use ++cmd++ instead of ++ctrl++.

## Where next

[Documents](documents.md) · [Build and log](compile.md) · [Findings](checks.md) · [Submission and packaging](submit.md) · [PDF preview](preview.md) · [Visual editor](editor-visual.md) · [AI agent](agent.md)
