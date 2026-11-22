---
title: Editing a copy and releasing
description: How to fix a released template version in Template Studio: "Edit a copy", the version number, the notes about changes and the release.
tags:
  - Templates
  - Pack authors
---

# Editing a copy and releasing

<p class="hds-lede">Every edit of a template comes out as a new version: a released one is not touched. The "Edit a copy" button makes a copy of the version for your edits without windows and questions, the Studio picks the number itself, and releasing a version is one tick in the "Changes" panel.</p>

What the numbers mean and how projects get an update: [Packs and templates, versions](../reference/pack.md).

## The course

1. **Edit a copy.** For a released version the main button of the strip is called "Edit a copy" (it is also in "Details" and next to the lock in "Content"). The Studio creates a copy of the version with the next number (a small fix: `2026.1.3` gives `2026.1.4`) and you stay on the same screen: the same student conditions, the same selected element, the same document and file in "Content". The base folder is copied, the notes are empty, the release mark is removed; the version is called "draft". If that number is already released in the main branch (someone was first), the Studio takes the nearest free one itself.
2. **Edits.** Edit conditions ("Change conditions" in "Details") and content ("Content"). Everything you changed is collected in the **Changes** panel: a group "New version 2026.1.4 and my edits" with the files that differ from the base (files of the copy that you did not touch do not count as edits).
3. **Number.** The Studio looks at your edits and picks the number itself: "These edits change the set of documents, the number will be 2026.2.0". If you need otherwise, **change the number** opens the "Version number" window with the size of the changes: **Small fix** (texts, files, signature places), **New features** (new without breaking anything: fields, documents, deadlines) and **New edition of the regulation** (another intake year, a number like `2027.1.0`). You cannot pick softer than the edits require, stricter you can. If the number is still softer than the edits suggest, write "Why this number": the explanation goes into the release description and into the merge request.
4. **What changed for students and supervisors.** A couple of short phrases, one item per line, in Russian and in English (the number of items must be equal). The notes are saved by themselves. If you do not write them, at sending the Studio fills in a suggestion from your edits ("Suggest notes and send"), and the **Suggest from changes** button gives a draft that you can read and fix. For deletions and tightenings there is a "What will stop working as before" field.
5. **Release the version.** The **Release version 2026.1.4** tick in the "Changes" panel. A released version is closed for edits: after the request is accepted students use it, and new edits go into its copy. Under "Advanced" there is **Make it the default version for new projects**. Without notes items in both languages the version cannot be released.

The version is released in your branch, and it becomes released for everyone after the merge request is merged ([Send for review](propose.md)). Until the merge the release can be repeated: if files changed after the release, the Studio releases the version again by itself at sending. In a folder on disk the release is final at once.

If at sending the Studio sees that the number is taken in the main branch, it offers a free one and moves the edits there.

## Move the edits { #move }

If the folder of a released version was edited bypassing the Studio (files changed in the repository or in the folder), it no longer matches the list of releases. Such edits are moved into a copy with the next number: in git the folder of the released version returns to the main branch, in a folder on disk you return it yourself (for example `git checkout`). Open the released version and the **Changes** panel: at the top there is a "Released version was edited outside the Studio" notice with a **Move the edits to 2026.1.4** button (the number is picked automatically). The Studio moves the edits and opens the new version.

The same on the command line: `hse-doc-studio pack new-version`, `pack classify`, `pack freeze`, see [Command line and CI](ci.md).

<!-- T15 (a pack and a template from scratch): a "New pack and new template" section here: stubs, a copy of a pack or a template with new ids. For now: the breadcrumb menu, "Create a pack" and "Create a template". -->
