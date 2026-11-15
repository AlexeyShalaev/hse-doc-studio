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
- Manifests (`version.yaml`, `doc.yaml`) have the **Source** and **Form** tabs. For now "Source" works: forms over YAML come in later releases.

<!-- T11–T14 (forms): a "Forms" section here, after "The editor": fields and groups, questionnaires, documents, submission profiles and the route, checks. Drop the sentence about "Form" above. -->

## Problems

The **Problems** panel shows the findings of the linter and the schemas for the saved files of the version: errors and warnings with the file and the line. A click opens the line. Blocks: **This file**, **Other files of the version**, **Whole version**. **Check again** reruns the check.

- The version files and the pack manifests (`pack.yaml`, `template.yaml`) are checked. Other files are not.
- What the linter checks: [Packs and templates](../reference/pack.md#pack-cli) and the sections for pack authors there.
- The **Checks before sending** block appears when "Propose changes" stopped on errors in the pack: fix them and propose again.

## Released versions

A version entered in the release registry (`releases.yaml`) of the main branch is immutable: student projects read its manifest, and an edit in place would silently change their requirements. So:

- the files of a released version open read-only, and schema errors in it are warnings;
- nobody edits the release registry by hand, the "New version" wizard keeps it;
- a fix ships as a new version: the **New version from this one** button above the editor, see [New version](versions.md).
