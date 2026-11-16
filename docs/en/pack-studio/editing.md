---
title: Editing a pack
description: The file tree, the code editor with completion, the Problems panel and why a released version cannot be edited.
tags:
  - Templates
  - Pack authors
---

# Editing a pack

<p class="hds-lede">On the left is the workspace tree: packs, templates, versions and their files. A file opens in the code editor, and saving checks the version with the linter and the schemas right away. Released versions open read-only: edits go into a new version.</p>

## The tree

- Each version shows its state; a released one has a lock.
- The **modified** mark on a released version means its folder was edited outside the Studio and no longer matches the release registry. Such edits move to a new version, see [New version](versions.md#move).
- **Reload the tree** if the files changed outside (for example, in a folder on disk).
- Images, fonts and office files are in the tree, but the editor does not open them.

## The editor

- **Save** writes the file. **Discard changes** brings back the saved text. The Studio will not let you leave a file with unsaved edits silently.
- If the file changed since you opened it (another tab, an edit in the folder), the Studio offers **Take their version**, **Keep mine** or **Compare**.
- Completion: in Jinja templates (`{{ }}`, `((* *))`) the context variables, the form fields `project.meta.<key>` and the pack filters; in the version's LaTeX the `\hse...` macros and the fields they print.
- Version and document manifests (`version.yaml`, `doc.yaml`) and rules files `checks/*.yaml` have the **Source** and **Form** tabs.

<!-- T11, T12 (forms): add fields and groups, questionnaires, documents to the "Forms" section below, next to "Submission and signing". -->

## Forms { #forms }

A form edits the same file as "Source" and the same way: every change goes to the YAML right away as a targeted edit (comments, alignment and keys the form does not know stay), then the checks and the version class are recalculated as after saving in the editor. A value the template would not understand is not written, and the form shows why. While "Source" has unsaved edits, the Form tab is closed: save or discard them first.

### Submission and signing { #submission }

The **Submission and signing** section of the `version.yaml` form:

- **Version signing order** (`signatures.route`): steps, within a step people sign in parallel. Signatures are dragged between steps, the same is available with the **With previous** and **Separate** buttons. Without an own order the built-in one applies: the authors, then the supervisor and the consultant, then the academic supervisor.
- **Checkpoints** as cards: identifier, name, description and the **deadline hint** (`deadline_hint`, both languages, up to 200 characters, no concrete dates: the form warns right away). A checkpoint can be added, moved and deleted.
- **Items**: the document, its signatures as checkboxes (only the slots that apply to the document) and the signing methods per slot (image, detached e-signature, PAdES; none ticked means any method), "Not submitted under NDA", the kind of work.
- **Files besides documents** (`extra_items`): a form from the list (the file name and format are filled in) or another project file. The form warns if a questionnaire goes into the package but is not marked as needed for it.
- **Checkpoint signing order** (`signing_route`): the checkpoint's own order instead of the version order.
- **Extra and optional signatures** (`signing_slots`): a document from the items, a signature, a condition from the list ("always", "if the supervisor is set", "set and from HSE", "set and from a company", the same for the consultant and the academic supervisor) and the **Optional** mark. A signature an item requires has no condition; a slot required in the catalog cannot be optional.
- **Route in this combination** under each checkpoint: see [Preview](preview.md#route).

Check findings about a checkpoint are shown right in its card. What the keys mean: [Packs and templates, signing presets](../reference/pack.md).

### Checks and rules { #checks }

- The **Checks** section of the `version.yaml` form (`checks_version`): turn a whole category off, turn a rule off, give a rule another severity in this version ("Do not check" too).
- The form of a rules file `checks/*.yaml`: the group name and the document reference (both languages; without them a project shows the group as a raw id), the source; rules as cards. A rule has an identifier (usually starting with the file name), a title and description, a category, documents ("All documents" or chosen ones), a severity and an engine. Structural checks have parameter fields (page margins, line spacing, font size, paragraph indent, page count), other engines take YAML text. Parameter keys the form does not know (for example `message`) stay.
- **Check on the preview**: pick a document and press **Build and check**. The document is built with the preview data set and switches, the version rules run with the same engine as in a project; findings show at their rules, rules that passed are marked "No findings". LanguageTool rules do not run on the preview.

## Problems

The **Problems** panel shows the findings of the linter and the schemas for the saved files of the version: errors and warnings with the file and the line. A click opens the line. Blocks: **This file**, **Other files of the version**, **Whole version**. **Check again** reruns the check.

- The version files, the pack manifests (`pack.yaml`, `template.yaml`) and the scenario files (`scenarios/<id>.yaml`, schema) are checked. Other files are not.
- Findings tagged "outcome" are the static rules of the outcome linter (a slot outside every route, `visible_if` on a value that does not exist, a missing translation and others): [Outcome linter and coverage](index.md#outcome-lint). The calculated rules and the scenario coverage come from a separate request.
- What the linter checks: [Packs and templates](../reference/pack.md#pack-cli) and the sections for pack authors there.
- The **Checks before sending** block appears when "Propose changes" stopped on errors in the pack: fix them and propose again.

## Released versions

A version entered in the release registry (`releases.yaml`) of the main branch is immutable: student projects read its manifest, and an edit in place would silently change their requirements. So:

- the files of a released version open read-only, and schema errors in it are warnings;
- nobody edits the release registry by hand, the "New version" wizard keeps it;
- a fix ships as a new version: the **New version from this one** button above the editor, see [New version](versions.md).
