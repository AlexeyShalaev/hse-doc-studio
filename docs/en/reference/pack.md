---
title: Packs and templates
description: The Studio is the engine, the pack is the content — everything about your work is declared by a template pack, with the version pinned at project creation.
tags:
  - Reference
  - Templates
---

# Packs and templates

<p class="hds-lede">The Studio is the engine; the pack is the content. Everything the product “knows” about your work — which documents exist, which standards they follow, what to check and what to submit — is declared in a pack, not hard-coded.</p>

Pack
:   A set of templates for an institution or a programme. A pack declares documents, metadata fields, check rules, forms and submission profiles — the app and this site read the same manifests.

Template
:   A type of academic work inside a pack — a graduation thesis or a course project, for instance. Each template has its own document set and its own submission points.

Version
:   A snapshot of the template's requirements. It is pinned in the project at creation: the requirements never shift under you mid-year, and moving to a newer version is a deliberate action.

Track
:   A branch inside a template (applied or research). It changes the document set: the template declares which documents exist on each track.

Language
:   A template's documents may exist in several languages; the work's language is chosen at project creation and defines which editions get built.

## What this buys you

- **Requirements cannot be broken “by accident”** — the document set, mandatory fields and check rules all come from a single source.
- **The product is not tied to one programme** — a different pack means different documents and points; the engine stays the same.
- **The numbers on the [landing page](../index.md) are not written by hand** — they are computed from the pack manifests when the site is built.

## Template versions and updates

A template version number is `YEAR.MINOR.PATCH`. The year is the intake whose regulations the version follows (2026 is the 2026/27 academic year); version `2026.1` reads as `2026.1.0`.

| Class | What changes | How it is offered |
|---|---|---|
| Fixes (patch) | Template bugs without new requirements: colours, typos, false check alarms | A card on the project overview |
| New features (minor) | New sections, documents, fields and submission profiles, renames that carry your data over | Only in project settings, "Template version" |
| New edition (major) | Next academic year's regulations | Only in project settings, only when you decide |

A released version never changes: a project created on it is built and checked against the same requirements until you update it yourself.

How an update works:

- **Preview.** Before updating you see what happens to every file: which ones update silently (you didn't edit them), which merge with your edits and where your decision is needed. For each file you can see what the template changes, what you changed and the result.
- **Conflicts.** If you and the template changed the same spot, choose: keep yours, take the template's, or merge with `<<<<<<<` markers to sort it out by hand. Yours is kept by default.
- **Nothing is lost.** Before updating, the Studio saves a project snapshot in Versions. The update can be reverted; edits made after it stay.
- **Compare with the template.** The same settings section shows which template files you edited. A file you rewrote entirely can be untracked so updates never touch it.

If a project is opened in an older Studio than the one that saved it last (or that Studio's pack lacks the project's template version), the project opens read-only and its data stays untouched.
