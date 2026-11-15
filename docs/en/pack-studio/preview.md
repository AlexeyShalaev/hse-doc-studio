---
title: Preview and signature places
description: Building a template version on sample data in different combinations, examples files and signature places with the mouse on the PDF.
tags:
  - Templates
  - Pack authors
---

# Preview and signature places

<p class="hds-lede">The "Preview" tab builds a document of the version the way a student gets it: on sample data and in the chosen combination (language, kind of work, team, supervisors). On the built PDF you can place signatures and date marks with the mouse.</p>

## Building

Open any file inside a version (a manifest, a document, a template) and the **Preview** tab:

1. **Document** of the version. A document absent from this combination is marked "not in this combination".
2. **Sample data**: an example file or an automatic set (below).
3. **Combination**: the language, the kind of work, the team (one author, a team of two or three), the supervisor (from HSE, from a company, not set), the consultant, the academic supervisor, NDA (if the version has one) and the first form fields with a choice or a checkbox. **Reset combination** brings back the values of the set.
4. **Build.** The build runs on a runner, as for projects: locally the embedded runner with Docker, on a server the installation runners within your quota.

Next to it are the PDF (**Open full screen**) and the **Log**. The same combination on the same files is not built twice, the PDF comes from the cache. If the files changed after a build, the Studio says so: build again. A person runs at most two preview builds at once, and a build can be cancelled with **Cancel**.

The first build waits for the TeX image. If LaTeX failed, the first line with "!" in the log points to the place; Jinja template warnings go to the log as `[render]` lines.

## Sample data { #examples }

Automatic sets are always there:

- **Typical**: values from the field placeholders and defaults;
- **Long values**: every string field three times longer, to see title lines overflow;
- **Empty**: only the fields required at creation, the rest prints as blanks.

Your own sets live in `templates/<template>/examples/<name>.yaml`, outside the version folders: editing them does not change the version and needs no release. The Studio does not read them when it creates projects.

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

- `lang`, `kind`, `staffing` are offered as combination values, you can switch them.
- People: `authors` (up to three), `supervisor`, `co_supervisor`, `academic_supervisor`; a person has `name`, `group`, `email`, `position`, `degree`, `role` (`university` or `company`).
- `meta`: form field values by their keys (strings, numbers, `true` and `false`).
- A set does not give questionnaire answers yet.

## Signature places { #places }

A successful build has the **PDF** and **Signature places** switch. In the second view the signature slot frames lie on the pages, with the slot catalog of the document on the right.

- Drag a frame to place it. The frame is shown at 3:1: in a project its height depends on the signature picture.
- **Own place of the document** or the slot's **Default place** (a pale frame marked "default"). **Make it the default place** turns the document's place into the shared place for all documents without their own, **Remove the document place** gives the document the default place back.
- If the template has signature lines (anchors), a new place lands on the slot's line and moves relative to it. **Snap to line** and **Unsnap from line** switch this explicitly. In a build without lines the fallback place moves.
- Date marks move the same way, **Mark on a date line** puts a mark on a template line, **Remove the mark** removes it.
- Places are rounded to a millimetre, the width is 10 to 200 mm, the frame stays on the sheet.

Place edits go into `version.yaml` as targeted edits: the rest of the text and the comments stay the same. Places and date marks are a patch change. In a released version places are view-only. How places look in the manifest: [Packs and templates, signing presets](../reference/pack.md).

Hints about places (off the sheet, a `per_author` place on a shared document, a place narrower than the detached signature plate) come to the **Problems** panel.

<!-- T13 (route forms): describe "Route in this combination" and pale slots outside the checkpoint route here, after "Signature places". -->
