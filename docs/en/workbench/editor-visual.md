---
title: Visual editor
description: Writing the work without learning LaTeX — Visual mode, template fields with Tab, the slash menu, image paste.
tags:
  - Workbench
  - Editor
---

# Visual editor

<p class="hds-lede">The editor has two modes — Code and Visual. Visual turns LaTeX into text that looks like text: formulas render, boilerplate folds into cards. It is the same file — switching is instant and lossless.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/documents/thesis?tab=source</span></div>
    <img src="../assets/shots/editor.en.light.png#only-light" alt="Visual editor">
    <img src="../assets/shots/editor.en.dark.png#only-dark" alt="Visual editor">
  </div>
  <figcaption>the visual mode: blocks, formulas and \hseFill fields</figcaption>
</figure>


## What it does

- **Filling in the template** — yellow <span class="hds-fill">\hseFill</span> fields, a “Fields left: N” counter, ++tab++ walks the unfilled ones; metadata (topic, supervisor, group) is stamped in at build time by itself.
- **Formatting** — a toolbar: styles, lists, headings, formulas rendered with KaTeX right in the text.
- **The slash menu** — `/` on an empty line: figure, table, citation, footnote, page break.
- **Image from the clipboard** — ++ctrl+v++ saves the file into the project and inserts a ready figure block with a caption.
- **Cards instead of boilerplate** — the preamble, table of contents and appendices fold away; title pages are “From template · read-only”, impossible to break by hand.
- **Tables and sources** — modal editors; the bibliography is honest `thebibliography` with no formatting loss.
- **Code mode** — CodeMirror with highlighting, autocomplete and squiggly finding underlines right in the code.

Editing the same file in VS Code is safe: the Studio notices and offers “Take from disk / Keep mine / Compare”.
