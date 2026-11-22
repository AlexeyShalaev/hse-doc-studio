---
title: Content
description: The "Content" tab of Template Studio: documents, text, signatures and places, project data, questionnaires, deadlines, languages, check rules, all files and why a released version cannot be edited.
tags:
  - Templates
  - Pack authors
---

# Content

<p class="hds-lede">The "Content" tab is everything you can edit in a template version: the "What we edit" list on the left, a form or text in the centre. Edits are written by themselves, checked at once, and the result on the "Result" tab is recounted. Released versions open read-only: the edits go into a copy of the version.</p>

## What we edit

The list on the left; on a phone it is a separate first-level page:

- **Documents**: every document of the version. With nine documents or more, the first six and the open one are shown and the rest are behind "N more"; there is a search.
- **Project data**, **Questionnaires**, **Deadlines and submission**, **Signatures and places**, **Languages**, **Check rules**: the sections of the version form.
- **All files** (for experts): the file tree of the version.

A document has three parts: **Terms** (when the document is in the set: kinds of work, staffing, languages), **Text** (the files of the document) and **Signatures**. On the right a document has the PDF preview: [PDF preview and signature places](preview.md).

## Text

- A file opens in a code editor and is **saved by itself** a couple of seconds after an edit; "saved" appears next to it. There is no "Save" button. **Restore as it was** brings the file back to how it was when you opened it.
- If the file changed since you opened it (another tab, an edit in the folder), the Studio offers **Take theirs**, **Keep mine** or **Compare**.
- Autocomplete: in Jinja templates (`{{ }}`, `((* *))`) the context variables, the questionnaire fields `project.meta.<key>` and the pack filters; in the LaTeX of the version the `\hse...` macros and the fields they print.
- Issues of the open file are shown above its text ("Line 5: …"), a click leads to the line. For a typo in a field name there is a **Fix** button.
- Files that do not open in the editor (images, fonts, office files) are not offered for editing.

<!-- T11, T12 (forms): fields and groups, questionnaires, documents and languages to be added to the "Forms" section below, next to "Deadlines and submission". -->

## Forms { #forms }

The form of a section edits the version description (`version.yaml`) or the document description (`doc.yaml`) the same way as the editor: every edit is written into YAML at once, pointwise (comments, alignment and keys unknown to the form stay), then the issues and the version number are recounted. A value the template would not understand is not written by the form, and it shows the reason. File names and short names are hidden under "Technical details", and the names in words are on view.

- **Documents**: the composition of the version, add, remove, reorder.
- **Project data**: the fields filled in when a project is created, and their groups. The name comes first, the short name of the field is next to it in small type: the template author prints it as `project.meta.<name>`.
- **Questionnaires**: the questions of the questionnaires and their fields.
- **Languages**: Russian and English, which the version has.
- **Check rules**: [below](#checks).

### Deadlines and submission { #submission }

The **Deadlines and submission** section (the version description, `version.yaml`):

- **Signing order of the version** (`signatures.route`): steps, within a step people sign in parallel. Signatures are dragged between steps, the same is done with the **With the previous** and **Separately** buttons. Without its own order the built-in one applies: authors, then the supervisor and the co-supervisor, then the academic supervisor.
- **Submission points** as cards: a name, a description and a **deadline hint** (`deadline_hint`, both languages, up to 200 characters, no concrete dates: the form warns at once). A point can be added, moved and deleted.
- **Items**: a document, signatures on it as ticks (only those that relate to the document) and signing methods per signature (an image, a detached e-signature, PAdES; with no marks any method), "Not handed in under NDA", the kind of work.
- **Files beyond documents** (`extra_items`): a questionnaire from the list (the file name and the format are filled in) or another project file. The form warns if the questionnaire goes into the package but is not marked as needed for the package.
- **Signing order of a point** (`signing_route`): the point's own order instead of the order of the version.
- **Signatures beyond the point and optional ones** (`signing_slots`): a document from the items, a signature, a condition from the list ("always", "if the supervisor is set", "set and from HSE", "set and from a company", the same for the co-supervisor and the academic supervisor) and the **Optional** mark. A signature required by an item has no condition; a signature required in the catalog has no "optional" mark.
- **Order in this situation** under each point: see [PDF preview and signature places](preview.md#route).

Issues about a point are shown right in its card. What the keys mean: [Packs and templates, signing presets](../reference/pack.md).

### Check rules { #checks }

- The **Check rules** section of the version description (`checks_version`): turn off a whole category, turn off a rule, give a rule another severity in this version ("Do not check" too). Categories are named in words, rule identifiers and the file name are under "Technical details" of the group.
- The form of a rules file `checks/*.yaml` (in "All files"): the group name and a link to a document (both languages, without them the group shows as a raw id in the project), the source; rules as cards. A rule has an identifier (usually with the file name at the start), a name and a description, a category, documents ("All documents" or chosen), a severity, an engine. The parameters of structural checks are fields (page margins, line spacing, font size, paragraph indent, number of pages), for the other engines YAML text. Parameter keys the form does not know (for example `message`) stay.
- **Check on the preview**: pick a document and press **Build and check**. The document is built on the chosen sample data and student conditions, the rules of the version run on the same engine as in a project; findings are shown at their rules, passed rules are marked "No findings". LanguageTool rules do not run on the preview.

### Signatures and places

The **Signatures and places** section shows which signatures a version has, and the "Signatures" page of a document puts them on the PDF: [PDF preview and signature places](preview.md#places).

## All files

For experts. The tree of the version: documents, shared parts, images, rules. A file opens in the editor (images, fonts and office files are visible in the tree but do not open). The form of a `checks/*.yaml` rules file has stayed on its earlier words. **Create a pack** and **Create a template** are in the breadcrumb menu at the top of the screen.

## Issues

Issues of the open file are shown above its text, and all of them at once are in "Check", "Issues" ([Check](index.md#check)). The files of versions and the pack descriptions (`pack.yaml`, `template.yaml`) are checked, as well as the files of ready cases (`scenarios/<name>.yaml`, the schema). Other files are not checked. What exactly the linter checks: [Packs and templates](../reference/pack.md#pack-cli) and the sections for pack authors there. Issues marked "result" are the result check rules: [Result check rules](index.md#outcome-lint).

If "Send for review" is stopped by errors in the template, the main button is called "Fix errors · N" and leads to "Check", "Issues": fix them and send again.

## Released versions

A version entered in the list of releases of the main branch (`releases.yaml`) is immutable: student projects read its description, an edit in place would silently change their requirements. So:

- the files of a released version open read-only (the screen shows a lock and the "Version … is released and does not change" note), and schema errors in it have the warning level;
- the list of releases is not edited by hand, sending for review keeps it;
- you can fix a version in a copy: the **Edit a copy** button (the main one in the strip, also in "Details" and next to the lock in "Content"), see [Editing a copy and releasing](versions.md). Any of these buttons makes the copy the same way and leaves you on the same screen.
