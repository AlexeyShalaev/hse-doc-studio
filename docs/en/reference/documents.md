---
title: Documents
description: The document as an entity — code, standard, mandatoriness, existence conditions, protected and custom files.
tags:
  - Reference
  - Documents
  - GOST
---

# Documents

<p class="hds-lede">A document is one unit of the set: it has its own code, its own files, its own status and build history. Which documents exist in your work is declared by the pack's template.</p>

What the template declares about every document:

- **Code** — the short cipher on the chip in the Documents panel.
- **Standard** — which GOST or format the document is built to; the rules that check it come from the same source.
- **Mandatoriness** — required documents are always in the set; the rest join depending on the nature of the work.
- **Existence conditions** — a document may exist only in team projects (a shared edition), only on one track, or only in one language.
- **Personal or shared** — in a team project, shared documents (`shared/`) live next to each author's personal set.

How a document lives in the project:

- **Template files are protected** — their content is refreshed from metadata at build time; they cannot be renamed or deleted.
- **A custom document** — any generated file can be replaced with your own (“Replace with your own file…”).
- **Metadata is stamped at every build** — unfilled mandatory fields stay in the PDF as the yellow <span class="hds-fill">\hseFill</span> highlight.

Working with documents — in the [Workbench](../workbench/documents.md); builds and the log — [here](../workbench/compile.md).
