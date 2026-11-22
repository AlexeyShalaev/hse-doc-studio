---
title: Template Studio
description: What Template Studio is, how to open it, how the screen works (Result, Content, Check, Changes) and where it takes templates from: a folder on disk, your own git repository or the official Studio templates.
tags:
  - Templates
  - Pack authors
---

# Template Studio

<p class="hds-lede">Template Studio is the section for people who edit document templates. It shows what a student gets when you change a condition; you edit the template in an editor, check it, build a PDF preview, place signatures with the mouse and send the changes for review. Students do not need it: they work with projects, not templates.</p>

How a pack (a set of templates for a programme), its versions and numbers work: [Packs and templates](../reference/pack.md).

## How to open it

| Where | How to turn it on |
|---|---|
| Local Studio | **Settings**, the "Template Studio" section, the "Template author tools" switch. A header button appears. |
| Server | An administrator turns the section on in `/admin`, "Template Studio", and grants access to a person or a group ("Who can edit templates"). Installation administrators always have access. |
| Template Studio only, on your computer | A launch profile with one command, without sign-in or projects: [Template Studio on your computer](../deploy/pack-studio-local.md). |

The section lives at `/pack-studio`. Turning it on does not change projects.

## Spaces

A space is the template source you work with: where the Studio takes the files from and where it sends the edits. You can have several. The list shows the state of each: "Connecting…", "Could not connect" (with the reason), "N files changed, not sent", "request #N is open" or "no changes".

The **Connect a space** button offers three ways:

- **Official HSE templates.** The simplest way: fix or improve the Studio templates and send the edits for review. More: [Send for review](propose.md#official).
- **Your own repository.** Your faculty's templates in git on GitHub or GitLab. One field is on view, the repository address; under "Advanced" are the main branch, the templates folder inside the repository (`packs`, "." means the root), the name and the access. The Studio downloads only the templates folder, usually in a couple of minutes.
- **A folder on your computer** (local only). Edits are written straight to the folder, there is no sending for review: you make commits and push yourself.

Repository access is a token from **Settings**, the "Repository access" section (the **Add token** button). If there is no suitable token you can paste one right in the connect window, the **New token…** item: the Studio checks it and selects it at once. A public repository can be read without a token, but then you cannot send changes. What rights the token needs is shown by the "Repository access" window (the "More" menu of the "Changes" panel): it checks the token and helps to issue a new one.

On a server an administrator can connect a repository for all authors ("Connected repositories" in the "Template Studio" section of `/admin`). Then you can pick **Connected repository** when connecting: changes are sent with the access the administrator set up, commits are signed by you, your own copy of the repository (a fork) is not available.

The space menu (**More**): **Refresh** (take the fresh main branch and recount which versions are released) and **Delete**. Deleting removes the copy in the Studio, the repository on the hosting does not change, and for a folder on disk only the record is deleted. If there are unsent edits, the window warns that they will be lost.

## How the screen works { #screen }

A space opens on the right template version. At the top is a "what am I looking at" strip: **Pack**, **Template** and **Version** as breadcrumbs (it opens the version with your edits, or the one you were on last time, or the default version), and under it three tabs:

| Tab | What is in it |
|---|---|
| **Result** | What a student gets under the chosen conditions. "For which student", the parts of the result and "Details" on the right. |
| **Content** | Everything you can edit: documents, project data, questionnaires, deadlines and submission, signatures and places, languages, check rules, all files. |
| **Check** | Issues of the template, "Typical cases", "What affects what", comparing two situations. |

Two buttons on the right of the strip are visible on every tab:

- **Changes** with a counter: what you changed and what is not sent yet. It opens the "Changes" panel: [Send for review](propose.md).
- **The main button**, always only one, which names the next step: **Edit a copy** (the version is released and does not change), **Describe changes**, **Fix errors**, **Send for review**, **Update request**. The Studio decides which step fits now: [Editing a copy and releasing](versions.md).

A version is marked **draft** or **released**. A released version cannot be edited, the edits go into its copy.

**Phone and tablet.** The same tabs sit at the bottom of the screen: **Result**, **Content**, **Check**, **Changes** (the badge shows the number of changed files). The breadcrumbs collapse into one button, "Coursework · 2026.1.3", which opens "Where to go" with a "My changes" shortcut (straight to your draft). "Details" slide in as a sheet, editing a condition works in full, "Content" is a list of sections and editing opens on the next page.

## Result { #outcome }

The **Result** tab shows what a student gets: documents and file names, project data, participants, deadlines and hand-in, signatures. The server counts it with the same code that creates projects; the screen writes nothing and sends nothing. Everything is counted on sample data.

### For which student { #situation }

The row of conditions at the top: the language of the work, the kind of work, the number of authors, the supervisor, the co-supervisor, the academic supervisor and other conditions of the template (the rest are under "N more conditions"). Change any of them and the result is recounted at once, and what changed is highlighted. The "What it changes" hint of a condition names the parts of the result it touches. Conditions that do not affect this template are collected separately under "Do not affect this template".

In the **More** menu of the row:

- **Reset conditions**: back to the defaults.
- **Remember this case**: save the conditions from the screen under a name so that you can pick them later in "Ready cases". Under "Advanced" you can also remember today's result: the Studio warns you when it changes.
- **Compare with another situation**: opens the comparison in "Check".

### Parts of the result

On the left are the parts of the result: **Documents**, **Project data**, **Participants**, **Deadlines and hand-in**, **Signatures**. Each shows how many elements it has, and the **Not in the set** block (and its kin) shows what is switched off under the chosen conditions, with a "Show when…" button: it finds the condition under which the element appears. For documents the search and the "All, Personal, Shared" filter appear when there are more than ten. The **PDF** button next to a document opens the preview: [PDF preview and signature places](preview.md).

### Details { #details }

Click a document, a field, a participant or a signature and **Details** open on the right:

- **Why it is so**: by which conditions the element got into the result, with a tick "the condition holds" or a warning and an explanation in words;
- **What changes if…**: which student condition to set differently so that the state of the element changes (one button sets that condition on the screen);
- **Change conditions**: a small form for editing the condition right here (which kinds of work, staffing and languages suit the document, when to show a questionnaire field, when a signature is needed, which checks are off). The edit is written into the version at once, the result is recounted and below you see what changed (`+` appeared, `~` changed, `-` disappeared). Next to it is **Remove the condition**: first the Studio shows how many elements it touches, and you can **Undo** for 10 seconds;
- **More**: **Undo the edit** and **Redo the edit** (`Ctrl+Z` and `Ctrl+Shift+Z`, a feed of the last 50 edits), **Edit history**, **Copy link to this element**;
- **Technical details** (collapsed): the condition file, the path in the version description, the source text.

For a released version, instead of "Change conditions" there is an **Edit a copy** button: the Studio makes the copy and you stay on the same screen, with the same conditions and the same selected element.

The screen needs the same access as the whole section. If the server does not support it (an older server, the `pack_outcome` flag in `bootstrap`), the space opens only on "Content".

## Ready cases { #scenarios }

A ready case is a named situation of a student, for example "one master's student, a supervisor from HSE" or "a team of three under NDA", and an optional expectation. Ready cases work as checks of the template: after an edit you see which of them "moved". The choice sits on the "For which student" strip (**Ready cases**), and the table of all cases is in "Check", "Typical cases". A badge next to a case says whether the result matches the expected one.

A ready case is a file `<pack>/templates/<template>/scenarios/<name>.yaml` next to `examples/`, outside the version folder. Editing it does not change the released version and needs no new release, it does not go to projects. The file lives in git and is reviewed like the rest; the Studio writes it itself (the "Remember this case" button) and writes nothing but this file when working with ready cases: no emails, no signatures, no invitations.

```yaml
format: 1
name:
  ru: Научрук из компании, есть консультант
  en: Company supervisor with a co-supervisor
example: auto:normal          # sample data; "Normal" without the key
versions: ["2026.1.*"]        # for which versions; empty: for any
inputs:                       # partial conditions, the rest by default
  supervisor: company
  co_supervisor: "yes"
assertions:                   # optional: pointwise expectations
  - { kind: route_steps, point: topic-approval, steps: [[author], [supervisor, co_supervisor], [academic_supervisor]] }
snapshot: { ... }             # optional: a compressed result, written by "Remember today's result"
```

- **Conditions** of a case lie between the version defaults and the conditions from the screen: first the defaults (and the sample data), then the case, then what is chosen on the screen. A condition that the version does not have, or a value outside the list, makes the case an error rather than refusing the write: a case outlives versions.
- **The expectation** is assertions (`document_state`, `document_count`, `meta_visible`, `participant_present`, `item_active`, `route_steps`, `route_pair`) and/or a snapshot of the result. Assertions are robust against unrelated edits, a snapshot catches everything and is noisy, so it is updated deliberately.
- **Checking** a case counts the result under its conditions on the chosen version and gives a state: `passed` ("The result matches the expected one"), `failed` ("The result changed", with a list of differences "expected, got" and of changes `+`, `~`, `-`), `error` ("The conditions of the case do not fit the version"), `unchecked` (neither assertions nor a snapshot, or the version is outside `versions`).
- **Deleting** is soft: the file is deleted, git keeps it in history, and writing the case again (without `If-Match`) brings back the same bytes.
- Up to 200 cases per template, up to 64 assertions per case, the file name is lowercase Latin letters, digits and a hyphen. The calculation is limited to five seconds and 20 calculations per second per person; if the version is too heavy or the server is busy you get "Try again later" (503 with `Retry-After`).

## Check { #check }

The **Check** tab answers the question "does the template work well". It has four sections:

- **Issues**: what is worth fixing in the template and whether the ready cases check it enough. Errors come first; an issue has a clear message, a "How to fix" hint, the affected parts of the result ("Show in the result"), up to three situations where it shows ("Where it shows") and an "Open the place in the file" link. The check number, the file and the place in the file are under "Technical details". The **Check template texts** button runs the heavy part (the template texts are built for a trial situation): it takes longer than the usual check, at most six times a minute, and only on your current edits.
- **Typical cases**: a table of "ready cases by parts of the result". A cell shows whether it matches the expected result, changed or is not checked; equal letters in a column mean the cases do not differ in that part. You can compare with the expected result or with the version before your edits (for a space with history), and the **Check again** button recounts.
- **What affects what**: which student conditions change the result and how many different variants of the result come out of that. If there are too many variants you can **Fix** some conditions and the calculation fits the limit.
- **Compare with another situation**: two sides (ready cases, conditions from the screen, my last saved point or the main version against my edits) and a list of differences by parts of the result. Each difference shows its cause: the rule where to look and the values of the conditions. Cosmetics (file names, the language of the edition, availability of variants) is not among the differences.

Comparing with the main branch is impossible if the space has no history: a folder on disk has no git, the space has no main branch, a new version has no earlier one. Then the Studio answers "Nothing to compare with". These sections are limited to 20 seconds (the template check to 30), at most two at once per process and six requests a minute per person; an answer larger than 8 MiB is rejected ("Too many variants": fix some of the conditions).

### Result check rules { #outcome-lint }

Besides the usual check of files, the Studio looks in the version for what is visible only on the result: a signature that gets into no signing order, a step that waits for a person who is not there, a condition that never holds. These rules work on a closed condition language, so the answer is exact rather than "looks like". The findings are in "Issues" marked "result"; the full set is returned by `GET .../outcome/lint` and the MCP tool `pack_outcome_lint`. The rule for template texts is run by a button and only on your current edits: the texts are built in a separate process with time and memory limits.

| Rule | Severity | What it catches |
|---|---|---|
| `slot-never-routed` | warning | a signature of the catalog gets into the signing order of no point under any conditions |
| `route-step-without-person` | warning | a step of the signing order waits for a person who is absent under these conditions (for example `supervisor: none`) |
| `route-gap` | warning | a point requires signatures, and nobody can sign |
| `visible-if-unknown-field` | error | `visible_if` names a field that is not in the questionnaire |
| `visible-if-value-not-in-options` | error | `visible_if.equals` is outside the `select` options or not `true`/`false` for `bool` (including `yes` without quotes, which YAML reads as `true`) |
| `required-hidden` | error | a field or questionnaire field is required but hidden under any conditions |
| `field-never-visible` | warning | an optional field is hidden under any conditions |
| `variant-lang-outside-langs` | error | `supported_langs` of a document or variant names a language outside the version `langs` |
| `skip-if-nda-without-nda` | warning | `skip_if_nda` in a version without NDA |
| `when-unknown-person` | error | `signing_slots[].when.person` is not one of the three persons, the signature is not in the catalog or the document is not in the set |
| `when-never-held` | warning | the `when` condition does not hold under any conditions |
| `when-always-held` | info | the `when` condition always holds, it is redundant |
| `slot-when-overlap` | warning | two `signing_slots` records of one signature with different `when` hold together |
| `document-never-active` | warning | a document is in the set under no conditions |
| `item-never-active` | warning | a point item is handed in under no conditions although the document exists |
| `point-empty` | info | a point has no items (under some conditions or under all) |
| `translation-missing` | warning | a field, questionnaire, document, variant or signature lacks a translation of the name or hint into a language from `langs` |
| `builtin-gate-mismatch` | warning | a rule hardcoded in the engine (NDA, supervisors) does not agree with the version description |
| `dimension-no-effect` | info | a `select` or `bool` field affects nothing |
| `jinja-fail-open` | error | a template fails when built, while the project loader silently copies the file as is |
| `jinja-unknown-meta-key` | warning | a template reads `project.meta.<key>` that is not in `meta_fields` |
| `atlas-skipped` | info | there are more result variants than the limit, only the rules without enumeration remain |

If there are more than 2000 result variants, the rules that need enumeration are skipped: the answer carries the other findings and `atlas-skipped`.

**Which rules the ready cases check.** The universe is all the variants of the result, not only the defaults and switching conditions one by one. A rule is fully checked if the cases saw all its reachable outcomes ("the condition holds" and "the condition does not hold"; if only one is reachable, for example the condition always holds, it is enough), partly if some, not checked if none. The percentage is the share of the seen outcomes of all rules. In "Issues" this is a block with the percentage, the list of the partly checked rules and an "Add ready-made cases" hint: the situations that would check the most rules. The calculation is limited to 30 seconds, two at once per process and six requests a minute per person; the answer is cached and returns 304 by `ETag`.

## What next

- [Content: editing a template](editing.md): documents, data, questionnaires, deadlines, signatures, languages, check rules, text and all files.
- [PDF preview and signature places](preview.md): building a PDF under the student's conditions, sample data, signature places with the mouse.
- [Editing a copy and releasing](versions.md): how to fix a released version, the number, the notes, the release.
- [Send for review](propose.md): the "Changes" panel, the merge request, your own copy of the repository (a fork), hosting checks, official templates.
- [Command line and CI](ci.md): the same checks without the interface, CI of your own templates repository.

<!-- T15 (a pack and a template from scratch): a "New pack" section here, after "Official packs", and an item in "What next". For now "Create a pack" and "Create a template" are in the breadcrumb menu of the strip. -->
