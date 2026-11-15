---
title: New template version
description: The new version wizard of Template Studio: a copy of the base, the live change class, the number, the release notes and the release.
tags:
  - Templates
  - Pack authors
---

# New template version

<p class="hds-lede">Every template change ships as a new version: a released one is never touched. The wizard copies the base into a draft, keeps counting the change class (patch, minor, major) as you edit, suggests the number, drafts the release notes and releases the version.</p>

What the classes mean and how projects get an update: [Packs and templates, versions](../reference/pack.md).

## The course

1. **New version** at a template in the tree (or **New version from this one** above a released version). The base is the latest released version by default, the class sets the number: patch `2026.1.3` gives `2026.1.4`, minor gives `2026.2.0`, major asks for the intake year (`2027.1`). The base folder is copied into a draft with the `beta` status, the notes are empty and the `release` block is removed.
2. **Edits.** The bar above the editor shows the class of the draft. **Class reasons** open the list, a click leads to the file or the manifest. The class is recounted after every save.
3. **Number.** If the edits need more than the number gives (for example, a new required field in a patch version), the bar warns. **Number** moves the draft: a number softer than the minimum cannot be chosen, a stricter one can.
4. **Notes.** What changed for students and supervisors, ru and en in pairs, one item per line. **Use the report** drafts the items from the changes found. "What breaks" is filled for removals and tightenings. If the number is softer than the soft rules suggest (for example, a text edit the author treats as a patch), write the **Class explanation**: it goes into `release.note` and the PR description. The English translation is written by hand for now.
5. **Release.** The version becomes `stable`, gets a date and a class and goes into the release registry with the folder digest. The **Make it the default version for new projects** checkbox updates the template `default_version`. The linter does not let a version out without ru and en notes.

In a git workspace the release is an edit of the working branch: the version is released in the branch and becomes released for everyone after the PR is merged ("Propose changes"). Until then the release can be repeated: if the files changed after it, the bar offers **Release again**. In a folder on disk the release is final at once.

If the number is already released in the main branch (someone was faster), the Studio offers the next free number and moves the edits there.

## Move edits { #move }

If the folder of a released version was edited outside the Studio (the "modified" mark in the tree), there is a **Move edits to a new version** button above the editor. The edits are copied into a draft with the next number, and in git the released folder goes back to the main branch. In a folder on disk restore it yourself (for example, with `git checkout`).

The same on the command line: `hse-doc-studio pack new-version`, `pack classify`, `pack freeze`, see [Command line and CI](ci.md).

<!-- T15 (pack and template from scratch): a "New pack and new template" section here: starters, a copy of a pack or template with new ids. -->
