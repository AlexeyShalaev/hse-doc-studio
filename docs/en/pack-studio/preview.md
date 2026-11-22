---
title: PDF preview and signature places
description: Building a document of a template version under a student's conditions, sample data (examples files) and signature places with the mouse on the PDF.
tags:
  - Templates
  - Pack authors
---

# PDF preview and signature places

<p class="hds-lede">The PDF preview builds a version's document the way a student gets it: on sample data and under the conditions chosen on the screen ("For which student"). On the built PDF you can place signature places and date marks with the mouse.</p>

## Building

The preview opens in two ways: in "Content" it stands to the right of the document (on narrow screens with the **PDF preview** button in the document header, it slides in as a sheet), and on "Result" it is opened by the **PDF** button of a document in "Details".

1. **For which student**: the conditions come from the screen, the preview shows which of them are changed, and there is a **Change conditions** button. A document that is not in the set under these conditions is not drawn by the preview, which offers "Reset conditions" or "Show when…".
2. **Sample data**: a sample file or the ready-made sets (below).
3. **Document variant**, if the document has variants. Some variants produce no PDF.
4. **Build PDF.** Building works the same way as for projects: locally in the built-in Docker, on a server on the installation's build servers within your quota. While it builds you see "Building the PDF…" and a **Cancel** button.

Next to it are the PDF (**Full screen**) and the **Build log**. The same build on the same files is not repeated, the PDF comes from the cache. If the conditions or files changed after the build, the Studio says so: **Build again**. At most two builds run at once per person.

The first build waits for the TeX image. If LaTeX fails, the first line with "!" in the log points to the place; Jinja template warnings go into the log as `[render]` lines. If a document has no PDF (slides and similar files), the preview says so.

## Sample data { #examples }

Ready-made sets are always there:

- **Normal**: values from the hints and the default values of the fields;
- **Long values**: every string field three times longer, so you can see overflowing title lines;
- **Empty**: only the fields required at creation, the rest is printed as placeholders.

Your own samples lie in `templates/<template>/examples/<name>.yaml`, outside the version folders: editing them does not change the version and needs no release. The Studio does not read them when creating projects. A sample that cannot be read is named by the preview, which asks you to pick another.

```yaml
label: { ru: "Команда, руководитель из компании", en: "Team, company supervisor" }
name: { ru: "Контур согласования действий LLM-агента", en: "An Approval Gate for LLM Agents" }
lang: ru
staffing: team2
authors:
  - { name: "Иванов Иван Иванович", group: "МСПИН261" }
  - { name: "Петрова Анна Сергеевна", group: "МСПИН261" }
supervisor: { name: "Петров Пётр Петрович", position: "доцент", role: company }
meta:
  proposal_stage: "Предварительная"
```

- `lang`, `kind`, `staffing` are offered by the sample as values of the conditions, they can be switched.
- People: `authors` (up to three), `supervisor`, `co_supervisor`, `academic_supervisor`; a person has `name`, `group`, `email`, `position`, `degree`, `role` (`university` or `company`).
- `meta`: the values of questionnaire fields by their keys (strings, numbers, `true` and `false`).
- A sample does not set questionnaire answers yet.

## Signature places { #places }

In "Content" a document has a **Signatures** page: the signature frames lie on the PDF pages, and the list of the document's signatures is on the right. Everything is saved by itself.

- Drag a frame to the place you want on the page. The frame is shown in a 3:1 proportion: in a project its height depends on the signature image.
- **The document's own place** or the **shared place** of a signature (a pale frame marked "shared place"). **Make it the shared place** makes this document's place the shared one for all documents without their own, **Use the shared place** gives the document the shared one back.
- If the template has signature lines, a signature **follows the text**: it sits on the line and moves relative to it, so it does not get lost when the text shifts. **Stop following the text** leaves it where it is now. Without lines, signatures stand at fallback places and you move them yourself.
- Date marks move the same way, **Put the date on a line** puts the mark on a template line, **Remove date** removes it.
- Places are rounded to a millimetre, the width is from 10 to 200 mm, a frame does not leave the sheet. The exact place (page, millimetres from the edges) is under "Details".

Edits of places are written into the version description (`version.yaml`) pointwise: the rest of the text and the comments of the file do not change. Places and date marks do not change the composition of documents and count as a small fix. In a released version the places are view-only: next to the lock there is an **Edit a copy** button. How places are laid out in the version description: [Packs and templates, signing presets](../reference/pack.md).

Hints about places (beyond the sheet edge, a `per_author` place on a shared document, a place too narrow for the detached e-signature plate) come to "Issues".

## Signing order in this situation { #route }

In the "Deadlines and submission" section, under each point you can see which signing order a project gets with the people from the conditions on the screen: who signs by steps, which signatures the template added by condition (`signing_slots` with `when`) and which will not appear under these conditions, which signatures are optional, what the project author can add and which items are not handed in under these conditions. The same code that builds the order in a project counts it. The conditions are shared with "Result" and the preview: switch the supervisor to "From a company" in one place and the order and the build see it at once.

<!-- T13: pale signatures outside the point order on the PDF are not done yet; describe here when they appear. -->
