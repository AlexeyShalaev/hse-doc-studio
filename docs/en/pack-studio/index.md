---
title: Template Studio
description: What Template Studio is, how to open it and where it takes packs from: a folder on disk, your own git repository or the official Studio packs.
tags:
  - Templates
  - Pack authors
---

# Template Studio

<p class="hds-lede">Template Studio is the section for pack authors. There you edit a pack in an editor with checks, build a preview on sample data, place signatures with the mouse on the PDF, release a new template version and send the changes as a merge request. Students do not need it: they work with projects, not packs.</p>

How a pack, its versions and the patch, minor and major classes work: [Packs and templates](../reference/pack.md).

## How to open it

| Where | How to turn it on |
|---|---|
| Local Studio | **Settings**, the "Template Studio" section, the "Template author tools" switch. A header button appears. |
| Server | An administrator turns the section on in `/admin`, "Template Studio", and grants the "Template author" right to a person or a group. Installation administrators always have it. |
| Template Studio only, on your computer | A launch profile with one command, without sign-in or projects: [Template Studio on your computer](../deploy/pack-studio-local.md). |

The section lives at `/pack-studio`. Turning it on does not change projects.

## Workspaces

A workspace is the pack source you work with: where the Studio takes the files from and where it sends the edits. You can have several, each with its own file tree, branch and checks.

**New workspace**:

- **Folder on disk** (local only). The repository root or the packs folder itself. Edits go straight into the folder and there is no merge request: you commit and push yourself.
- **Git repository.** The repository address, the access, the base branch (empty: the server default branch) and the packs folder inside the repository (`packs`, "." means the root). The Studio clones only the packs folder; cloning takes up to a couple of minutes.

The repository access is a token from **Settings**, the "Repository access" section (**Add token** button). If there is no suitable token, paste one right in the creation dialog, **New token…** item: the Studio checks it and selects it right away. The token never lands in the clone. For branches and merge requests it needs write access, merge requests and reading the check status; the link "Which token branches and pull requests need" in the creation dialog lists the rights, and the "Repository access" dialog of the git panel checks the token and helps issue a new one. A public repository can be read without a token, but then a branch cannot be pushed.

On a server an administrator can set a service access for a repository ("Service access" in `/admin`). Then a new workspace can use **Service access**: branches are pushed with the installation token, commits are signed by you, forks are not available.

The workspace menu:

- **Update base**: fetch the fresh base branch and recount the released versions.
- **Delete**: removes the clone in the Studio (the repository on the hosting stays as is) or only the record of a folder (the folder on disk stays).

## Version outcome { #outcome }

A workspace opens on the **Outcome** screen: what a student gets for the chosen inputs (language, work kind, staffing, supervisors, NDA, fields, questionnaire answers, document variants). That is the documents and file names, the project fields, the participants, the submission points and the signing route. The server calculates it with the same code that creates projects; the screen evaluates no conditions and writes or sends nothing.

- **Outcome from**: the working tree (the default, with unsaved edits), the last commit of the branch or the base (the tip of the base branch). The commit and the base are read from the workspace git without switching branches. A folder on disk has neither, and neither has a new version that is not in the commit or in the base: the screen answers "Nothing to compare with".
- While the version manifests (`version.yaml`, the `doc.yaml` of the documents, the data set file) are unchanged, a repeated request returns the stored answer and is not recalculated.
- The calculation is limited to five seconds. If the version is too heavy or the server is busy with other calculations, you get "Try again later" (503 with `Retry-After`); the rate is limited to 20 calculations per second per person.
- **"Why?"**: for any element of the outcome (a document, a field, a submission point item, a participant, a route step or slot, a check rule) the server returns the chain of decisions from the conditions to the result: each rule has a status (held, not held, skipped), its place in the manifest (file and path), the condition and the actual input values; the neighbouring elements the same rules concern; and "What if": which single input to set to another value to change the state of the element. The answer is cached like the calculation; nothing is written.
- **"Edit rule"**: a manifest rule in the "Why?" chain has an edit button. It opens a mini-form of that record right in the panel (kinds of work, staffing and languages of a document, the visibility condition of a questionnaire field, the condition of a signature slot, skipping an item under NDA, an optional signature, disabled checks) without leaving the screen. Every edit is written at once to `version.yaml` or `doc.yaml` as a precise YAML edit with `If-Match` (comments and order stay), the outcome is recalculated and a comparison appears above the panel: what changed in the outcome, with the signs `+`, `~`, `−`. Editing a released version is off (create a new version), and so is editing a commit or the base; on a phone the rules are read-only.
- **Undo and redo**: "Undo" and "Redo" in the panel and `Ctrl+Z` and `Ctrl+Shift+Z` walk the edit history of this screen (up to 50, reset when the version changes). The undo returns the file with its former text byte for byte if it was not touched after the edit; otherwise it writes the inverse edit of the value. If the record was changed meanwhile, the Studio warns and asks. "Remove the condition" and "Delete the slot or item" first show how many outcome elements the record affects, then delete, and "Undo" in the toast works for 10 seconds; the history keeps the trace.
- The screen needs the same "Template author" right as the whole section. If the server does not support it (an older server, the `pack_outcome` flag in `bootstrap`), the workspace opens on "Files": the tree, the editor, the preview. "Files" can also be opened when supported: `?view=files`.

## Scenarios { #scenarios }

A scenario is a named point in the space of inputs, for example "one master's student, a university supervisor" or "a team of three with an NDA", with an optional expectation. Scenarios work as regression tests of a pack: after a rule edit you see which of them moved.

A scenario is the file `<pack>/templates/<template>/scenarios/<id>.yaml` next to `examples/`, outside the version folder. Editing it does not change a released version, needs no new release and is not copied into projects. The file lives in git and is reviewed like the rest; the Studio writes it itself (canonical YAML, an edit goes by `If-Match` like any file) and writes nothing else when you work with scenarios: no emails, no signatures, no invitations.

```yaml
format: 1
name:
  ru: Научрук из компании, есть консультант
  en: Company supervisor with a co-supervisor
example: auto:normal          # the data set; without the key the "Typical" auto set
versions: ["2026.1.*"]        # which versions it is for; empty: any
inputs:                       # partial, the rest is the defaults
  supervisor: company
  co_supervisor: "yes"
assertions:                   # optional: point expectations
  - { kind: route_steps, point: topic-approval, steps: [[author], [supervisor, co_supervisor], [academic_supervisor]] }
snapshot: { ... }             # optional: the compact outcome, written by the button
```

- **Inputs** lie between the version defaults and the request inputs: first the defaults (and the data set), then the scenario, then what is chosen on the screen. An input that the version does not have, or a value outside the list, makes the scenario an `error` instead of refusing the write: a scenario outlives versions.
- **The expectation** is assertions (`document_state`, `document_count`, `meta_visible`, `participant_present`, `item_active`, `route_steps`, `route_pair`) and/or a snapshot. Assertions are robust against unrelated edits, a snapshot catches everything and is noisy, so it is updated on purpose.
- **A run** calculates the outcome for the scenario inputs on the chosen version and state (working tree, last commit, base; scenarios are read from the same state) and gives a status: `passed`, `failed` (a list of mismatches "expected, got" and of `+`, `~`, `-` changes against the snapshot), `error` (the inputs do not fit the version or the file cannot be read) and `unchecked` (no assertions and no snapshot, or the version is outside `versions`). The coverage comes with it: which rules of the version saw both outcomes (held and not held), which saw one.
- **Delete** is soft: the file is removed, git keeps it in history, and writing the scenario again (without `If-Match`) brings the same bytes back.
- Up to 200 scenarios per template, up to 64 assertions per scenario, an `id` is lowercase Latin letters, digits and hyphens. The calculation has the same five-second limit and the same rate as the version outcome.

## Comparing outcomes and before and after { #compare }

Three requests show what will change in the outcome. All of them only read: they write nothing, build nothing and send nothing.

- **Compare** takes two sides (each one: a state, a scenario, an example, inputs on top of the scenario) and shows the changes by section and element: `+` appeared (a document entered the bundle, an item became active, a field became visible, a route step or pair was added), `-` disappeared, `~` changed (a route step has other people, a pair has another source, an item has other signatures; `~` shows "was" and "became"). The two sides can be on one state (two sets of inputs, two scenarios) or on two: the same combination in the working tree against the last commit or the base. Every change carries reasons from the trace: the rule (file and path in the manifest), its verdict on the left and on the right and the actual values of the inputs. If the rule itself was edited, there is one reason, with the "after" condition. Cosmetics (file names, the language edition, variant availability) are not in the changes, as they are not in the outcome fingerprint; checks (applicability of rules) are.
- **Before and after** runs the template scenarios on the base (the tip of the base branch; the last commit can be used instead) and in the working tree and answers "the outcome changes in N of M scenarios": each scenario has the status `unchanged`, `changed` (a list of changes) or `error` (the scenario cannot be read on one of the sides, for example an input appeared only in the new version; the message names the side). Unless turned off, it also gives the number of atlas table rows whose outcome differs on the base and the number of outcomes before and after (an atlas that is too large leaves the field empty). A scenario outside its `versions` is not part of the calculation. This is the basis of the "Propose changes" step.
- **The matrix** is the table "scenarios by sections": a cell has the fingerprint of the section structure, the element count and a status: `matched` (the scenario expectation for this section holds), `changed` (does not hold, or the section differs from the base when compared with the base), `unchecked` (the section has no expectation), `error` (there is no outcome). Cells with one fingerprint in different scenarios show that the scenarios do not tell the section apart. When compared with the base, a cell also shows whether it changed against the base.

The base may be missing: a folder on disk has no git (`no_git`), the workspace has no base branch (`no_base`), the version is not in the base because it is new (`new_version`). Then a request with the state `base` or `head` answers "Nothing to compare with" (`diff_base_unavailable` with the reason); the working tree is always calculated. "Before and after" and the matrix calculate each scenario twice, so they have a 20-second limit, at most two such calculations at a time per server and a rate of 6 requests per minute per person; comparing two sides runs under the outcome limit (5 seconds, 20 per second). A response over 8 MiB is refused (`outcome_too_large`): choose fewer scenarios. Responses are cached while the version, the base and the scenario files stay the same.

## Official packs

The **Official packs** card on the section's main screen opens the packs from the Studio's own repository. You need no repository of your own: edits go to your fork on GitHub and the PR is opened from your account. More: [Propose changes](propose.md#official).

## What next

- [Editing a pack](editing.md): the tree, the editor, "Problems", released versions.
- [Preview and signature places](preview.md): builds on sample data, combinations, signature frames on the PDF.
- [New version](versions.md): the change class, the number, the notes, the release.
- [Propose changes](propose.md): the branch, a PR or an MR, forks, hosting checks.
- [Command line and CI](ci.md): the same checks without the interface, CI for your packs repository.

<!-- T15 (pack and template from scratch): a "New pack" section here, after "Official packs", and an item in "What next". -->
