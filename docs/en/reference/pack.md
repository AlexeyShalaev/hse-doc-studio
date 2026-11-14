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
:   A type of academic work inside a pack — a graduation thesis or a course project, for instance. Each template has its own document set and its own checkpoints.

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
| Fixes (patch) | Template bugs without new requirements: colours, typos, false check alarms, form fixes; optional fields that change nothing in the output when empty; signing presets and deadline hints (below) | A card on the project overview |
| New features (minor) | New sections, documents, required fields or fields that change the output, submission profiles, renames that carry your data over | Only in project settings, "Template version" |
| New edition (major) | Next academic year's regulations | Only in project settings, only when you decide |

Besides fixes, the patch class covers signing presets and deadline hints: the order of signers, signature places and dates on the pages, signatures needed only under certain conditions (for example, when the supervisor is not from HSE), optional signatures, and a hint on when a checkpoint deadline usually falls. Template files and requirements do not change. Presets apply to new signing routes; signature places you set yourself and routes already sent are left as they are.

The patch class also covers form fixes and optional fields that change nothing in the output when empty. A form fix brings a document in line with the official form or the project data: for example, the city and the year come from the settings instead of being hard-coded in the template, and an “if any” line is printed only when the project has such a person. An optional field in a patch only refines such a form: an empty field leaves the document as the fixed form made it (for example, “City in English” is empty and the city is translated automatically). A field the document cannot be built without, or one that changes the document as soon as the project is created, is a minor.

A released version never changes: a project created on it is built and checked against the same requirements until you update it yourself.

How an update works:

- **Preview.** Before updating you see what happens to every file: which ones update silently (you didn't edit them), which merge with your edits and where your decision is needed. For each file you can see what the template changes, what you changed and the result.
- **Conflicts.** If you and the template changed the same spot, choose: keep yours, take the template's, or merge with `<<<<<<<` markers to sort it out by hand. Yours is kept by default.
- **Nothing is lost.** Before updating, the Studio saves a project snapshot in Versions. The update can be reverted; edits made after it stay.
- **Compare with the template.** The same settings section shows which template files you edited. A file you rewrote entirely can be untracked so updates never touch it.
- **Template signature places.** If the version sets signature places on the pages, the update moves the places you did not touch to the new version and says in the preview “Template signature places will be updated: N” and “Not updated: changed by you N, on a signing route N, signed N”. Places you set or moved yourself and documents under a signing route are left alone; undoing the update brings the places back. More: [Route from the template](../workbench/send-for-signing.md#preset).

If a project is opened in an older Studio than the one that saved it last (or that Studio's pack lacks the project's template version), the project opens read-only and its data stays untouched.

## For pack authors: signing presets

A checkpoint's route preset is set in the template version's `version.yaml`. All keys are optional: a version without them works as before, and a Studio that does not know a key skips it.

| Key | Where | What it sets |
|---|---|---|
| `signatures.route` | version | the route steps: `[[author], [supervisor, co_supervisor], [academic_supervisor]]`, signers within a step sign in parallel. Without it: the authors, then the supervisor and the consultant, then the academic supervisor |
| `signing_route` | submission profile | this checkpoint's steps instead of `signatures.route` |
| `default_placement` | slot | the signature place `{page, x_mm, y_mm, width_mm}` on documents without their own entry in `placements` |
| `placements` | slot | the signature place per document: `{document_id: {page, x_mm, y_mm, width_mm}}` or on a template line `{anchor, ...}` (below, "Places on the template lines") |
| `default_dates` | slot | date marks per document: `{document_id: [{page, x_mm, y_mm, width_mm, height_mm, format, align}]}`; a mark can sit on an anchor too |
| `signatures.anchor_macros` | version | template wrappers that pass the anchor name as their first `[...]`: the linter counts their calls as anchors |
| `signing_slots` | submission profile | signatures beyond the checkpoint's items, when they appear, and whether they are optional on the checkpoint |
| `required: true` | slot | this slot's signature cannot be marked optional on any checkpoint |
| `deadline_hint` | submission profile | a hint on when the checkpoint deadline usually falls: `{ru, en}` text, without concrete dates |

Coordinates are millimetres from the top left corner of the page, pages count from 1. A signature place is 10 to 200 mm wide, inside the width of an A4 sheet (210 mm), with its top between 0 and 287 mm; its height depends on the signature image.

```yaml
signatures:
  slots:
    - id: supervisor
      applies_to:        [project_proposal, topic_application, report]
      default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 }
      placements:
        project_proposal:  { page: 1, x_mm: 80,  y_mm: 139, width_mm: 40 }
        topic_application: { page: 1, x_mm: 163, y_mm: 168, width_mm: 40 }
      default_dates:
        project_proposal:
          - { page: 1, x_mm: 81, y_mm: 156, width_mm: 7,  height_mm: 5, format: day }
          - { page: 1, x_mm: 90, y_mm: 156, width_mm: 24, height_mm: 5, format: month_word }

pack_submission:
  profiles:
    - id: topic-approval
      items:
        - doc_id: topic_application
          signatures: [author, supervisor]
      signing_slots:
        - { doc_id: topic_application, slot_id: co_supervisor, when: { person: co_supervisor } }
        - { doc_id: topic_application, slot_id: academic_supervisor, when: { person: supervisor, role: company } }
```

A `signing_slots` entry:

- `doc_id` is a document from the profile's `items`, `slot_id` a catalogue slot that applies to that document (`applies_to`);
- if the pair is not in the item's `signatures`, it is a signature beyond the checkpoint: the route adds it by itself;
- `when` only on a signature beyond the checkpoint: `{person: <role>}` the person is set in the project, `{person: <role>, role: university | company}` set and from HSE or from a company. Roles: `supervisor`, `co_supervisor`, `academic_supervisor`. Without `when` the signature is always added. The Studio skips an entry with any other condition entirely, so that it never adds a signature nobody needs;
- `optional: true` the signature is optional on this checkpoint (both for a checkpoint pair and for a signature beyond it); not allowed on a slot with `required: true`.

The deadline hint `deadline_hint` needs both locales, at most 200 characters and no concrete dates: “Usually mid-November; the exact date is announced in SmartLMS”. A date like “15.11”, a day with a month name or an ISO date is an error for the linter: deadlines change every year and a released version does not. The deadline itself is set by the student on the checkpoint page ([Submission deadline](../workbench/submit.md#deadline)).

A preset does not set the signing method: the signer picks it from the methods the checkpoint item allows (`methods`). Nor does it set people: they are project data.

The Studio applies the preset when the author first prepares the checkpoint's route, and leaves places the author set or moved alone. Presets can ship as a patch version: it differs from the previous one only in these keys and in `signatures.route` and `signing_route`, with the same template files and requirements. The exception for files is `common/anchors.tex` and anchor calls that do not change the PDF (below, "Reproducible build"). Anything else makes it a minor.

Check before releasing: `python -m hse_doc_studio.infra.template.pack_lint <version directory>`. The linter reports as errors a box past the edge of the sheet, a place or marks on a document outside the slot's `applies_to` or outside the version's documents, a `signing_slots` entry whose document is not in the checkpoint or whose slot is unknown or does not apply, a repeated pair, `when` on a signature the checkpoint already requires, and `optional: true` on a slot with `required: true`. It warns when a signature beyond the checkpoint is missing from the route order (it will go as the last step), when a `per_author` slot has a place on a shared document of a team template, and when a place is narrower than the detached e-signature plate where the checkpoint allows one (the box will widen leftwards to 70 mm). Whether a box lands on the right line the linter cannot know: build the documents and look at the boxes on the Signatures tab.

You do not have to retype coordinates. Place the boxes and date marks on a built document of a live project, then open the "⋯" menu on the Signatures tab and choose "Copy as template preset". The Studio copies a `signatures.slots` fragment with `placements` and `default_dates` of this document or of every project document: document and slot ids as in the pack (a team member's document `report--ivanov` becomes `report`), coordinates rounded to 1 mm. Custom project signatures, disabled places and boxes the pack loader would reject stay out of the fragment, and the dialog lists them as warnings. The fragment carries no names of people and no project name.

### Places on the template lines (anchors)

The layout of a document depends on the project data: the English application has a shorter header, the consultant row is printed only when a consultant is set, a long title moves the date row down. A place in millimetres fits one layout only. So a place can be tied to a line of the template itself: a macro next to the signature line records where that line is when the document is built, and the Studio puts the box there.

1. Put `common/anchors.tex` into the version: a byte-for-byte copy of the Studio reference (`services/api/hse_doc_studio/infra/compile/tex/anchors.tex`). Load it in the document after the shared files: `\input{../common/anchors}`.
2. Put the anchor right before the line: `\hseSignAnchor[\linewidth]{supervisor}\rule{\linewidth}{0.4pt}` for a signature and `\hseDateAnchor[8mm]{supervisor}{day}\rule{8mm}{0.4pt}` for a part of the date row. The optional argument is the line width; without it the anchor is a point. A signature anchor is named by the catalog slot id, a date anchor by a "name, part" pair where the part is the mark format by convention (`day`, `month_word`, `month_number`, `year`, ...). The macro prints nothing in the PDF.
3. Template wrappers pass the name as their first optional argument (`\hseSignField[supervisor]{0.15\textwidth}{Signature}`) and are listed in `signatures.anchor_macros`, so that the linter sees their calls.
4. In `version.yaml` write the anchor instead of coordinates. This is how `hse-cs-sse/coursework` 2026.1.5 does it:

```yaml
signatures:
  anchor_macros: [hseSignField, signdateblank]
  slots:
    - id: author
      default_placement: { page: 1, x_mm: 160, y_mm: 208, width_mm: 30 }
      placements:
        # Application: the right edge of the box at the end of the "Signature" line, the top 11 mm higher.
        topic_application: { anchor: author, align: right, dy_mm: -11, width_mm: 30, page: 1, x_mm: 165, y_mm: 201 }
        # Report title page, "Signature, date": the box at the left end of the line, the date at the right end.
        report:            { anchor: author, align: left, dx_mm: 1, dy_mm: -11, width_mm: 28, page: 1, x_mm: 120, y_mm: 223 }
      default_dates:
        report:
          - { anchor: author.date_numeric, align: right, dx_mm: -1, width_mm: 20 }
    - id: supervisor
      default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 }
      placements:
        # Project description, item 6: the anchor at the start of the date row, the box in the empty cell above it.
        project_proposal:  { anchor: supervisor, align: left, dx_mm: 30, dy_mm: -22, width_mm: 40, page: 1, x_mm: 110, y_mm: 131 }
        topic_application: { anchor: supervisor, align: right, width_mm: 28, page: 1, x_mm: 168, y_mm: 177 }
      default_dates:
        # The Russian row "« __ » ______ 2026 г." and the English "__.__.2026": a mark whose anchor is not in the build is not placed.
        project_proposal:
          - { anchor: supervisor.day }
          - { anchor: supervisor.month_word }
          - { anchor: supervisor.month_number }
    - id: academic_supervisor
      # The consent line is printed only when the supervisor is not from HSE.
      default_placement: { anchor: academic_supervisor, align: right, width_mm: 28, page: 1, x_mm: 168, y_mm: 216 }
```

| Field | Meaning | Default |
|---|---|---|
| `anchor` | anchor id in the document: `supervisor` for a signature, `supervisor.day` for a date mark | required |
| `align` | how the box sits on the line: `left` (left edges together), `center`, `right` (right edges together) | `center` |
| `dx_mm` | horizontal shift after alignment, -200 to 200 | 0 |
| `dy_mm` | top of the box relative to the line, negative is higher, -287 to 287 | -10 for a signature; minus the height for a date mark (the mark stands on the line) |
| `width_mm` | box width: 10 to 200 for a signature | the line width, at least 10 for a signature |
| `height_mm`, `format` | for a date mark: height 2 to 20 and the format | 5; the anchor part if it is a format |
| `page`, `x_mm`, `y_mm` | fallback place in mm (with `width_mm`) while the build anchors are unknown | none: no place without anchors |

How the Studio places it: the build anchors are known and the anchor is there, the box follows the line; known but the anchor is missing, so the document has no such row, and there is no place; unknown (the document is not built, it was built by an older runner, the PDF came from the local Studio), so the fallback place in mm if it is set, otherwise no place. An uploaded PDF of your own gets no anchored place at all: a person places it. A date mark whose anchor is not in the build is not placed, so one entry covers both the Russian and the English date row. An anchored `default_placement` needs the full fallback place in mm: every Studio version reads it.

After every build the template places nobody moved follow the lines of the new build; if the line is gone, the place is switched off. Manual places, documents on a signing route (their place changes only with "Send a new version"), documents with an e-signature over the frozen PDF and uploaded PDFs are left alone.

#### `anchor_macros` wrappers

A template usually draws its signature lines with its own macro, and the anchor is easier to put inside it. The wrapper takes the anchor name as its first optional argument and prints the line as before without it. From `hse-cs-sse` 2026.1.5:

```latex
% topic_application.tex: a "Signature" line with the slot anchor
\newcommand{\hseSignField}[3][]{%
  \begin{minipage}[t]{#2}\centering
    \if\relax\detokenize{#1}\relax\else\hseSignAnchor[\linewidth]{#1}\fi%
    \rule{\linewidth}{0.4pt}\\[-2pt]{\footnotesize\itshape #3}
  \end{minipage}}
\newcommand{\hseSupervisorSign}[1]{\hseSignField[supervisor]{0.15\textwidth}{#1}}

% common/meta.tex: the date row with day and month anchors; without common/anchors it prints as before
\newcommand{\hseIfAnchor}[2]{\if\relax\detokenize{#1}\relax\else\ifdefined\hseDateAnchor#2\fi\fi}
\newcommand{\signdateblank}[1][]{«\hseIfAnchor{#1}{\hseDateAnchor[0.8cm]{#1}{day}}\rule{0.8cm}{0.4pt}» \hseIfAnchor{#1}{\hseDateAnchor[2.5cm]{#1}{month_word}}\rule{2.5cm}{0.4pt} \hseFormYear~г.}
```

List the wrapper names in `signatures.anchor_macros` (without the backslash): the linter counts a `\hseSignField[supervisor]` call as the `supervisor` anchor and takes a wrapper's date parts from its definition in the document files or in `common/` (for `\signdateblank[supervisor]` these are `supervisor.day` and `supervisor.month_word`). If the same line is on both the Russian and the English page of one file, move it into its own macro, like `\hseSupervisorSign` above: otherwise the anchor appears twice in the file and the linter warns about the repeat.

#### Fallback place

The `page`, `x_mm`, `y_mm` fields together with `width_mm` on an anchored entry are the fallback place: the Studio puts the box there while the build lines are unknown. That happens if the document is not built yet, if a runner older than 0.27.0 built it, or if the PDF was uploaded to the server from the local Studio. The fallback place works in Studios before 0.27.0 too: they read an entry with it as a plain place in mm, and drop an anchored entry without millimetres in favour of `default_placement`.

- Take the fallback place from the most common layout. In `hse-cs-sse` 2026.1.5 it is the Russian application without the consultant line, with millimetres taken from a build.
- An anchored `default_placement` without a full fallback place is a linter error: image upload and the signer page read it in every Studio version.
- Date marks can do without a fallback place. The course project has none on purpose: the Russian and English date rows differ, and a fallback mark would land on the wrong row. Without a fallback place the mark simply appears after a build.
- If the build lines are known and the anchor is missing, the fallback place does not apply: the document has no such line, so there is no place.

#### Reproducible build

Anchors do not change the PDF: `\savepos` and `\write` put nothing on the page, and PDFs with and without anchors are byte for byte the same. So a patch version that only adds anchors does not give "There are changes" on documents out for signing. The patch class check lets `common/anchors.tex` and anchor calls through as file changes.

To keep the PDF the same between builds too, the Studio calls latexmk with `-latexoption=-output-comment=hse-doc-studio`. Without it TeX writes the build date and minute into the XDV header, and xdvipdfmx puts them into the document `/Creator` when the document has no hyperref. A document rebuilt without edits in a different minute then gave a different PDF and a false "There are changes". If you compare PDFs of two pack versions outside the Studio, pass latexmk the same option and `SOURCE_DATE_EPOCH`. On the server runners 0.27.0 and newer build this way.

You do not need to place boxes by millimetres by hand: build a document with anchors, drag the box on the Signatures tab and choose "Copy as template preset" in the "⋯" menu. An anchored template place goes into the fragment as the pack entry as is, and a manual place is written relative to the slot anchor on the same page (`align: left`, `dx_mm`, `dy_mm`) with a `# by the build:` comment and the millimetres of this build. If the build has no anchors, the place is written in mm with a `# no anchor` comment.

The linter checks that every anchored entry has an anchor call or a call of a wrapper from `anchor_macros` with that name in the document files or in `common/`, that `common/anchors.tex` exists and the document loads it, and that an anchored `default_placement` has its fallback place. It warns when an anchor name in the sources is not a catalog slot id (a typo) and when one name appears twice in a file (the place follows the first one). The linter does not see an `\if` around an anchor: build the document with every combination of the data and check the boxes on the Signatures tab.

## For pack authors: the class of a new version

The pack linter works out the class of a new version from its contents: it compares the version with the previous released version of the template. There are two kinds of rules.

- **Hard** rules set the minimum. A new document, field, field group, form, submission profile, checkpoint item, signature slot, check rule or check file, language, work kind, staffing or build setup (`engine`, `latex_packages`, `dynamic_includes`) is minor. Removing a document, field, profile, slot or form is minor too, and major is suggested until there is a data migration declaration. Signing presets, deadline hints and the texts of labels and hints are patch.
- **Soft** rules only suggest a class. Edits to template files and check settings are patch, and the author may raise them to minor. A change to `methods` of an item, to `default_placement` of a slot or to field defaults suggests minor. A new optional field (`required_at: never`, no `default` and no `auto`) suggests patch when it keeps the output while empty.

The version number and `release.kind` cannot be softer than the minimum: the linter reports such a version as an error. When a soft rule suggests more than you release, the linter warns. Explain the choice in `release.note`, and the explanation goes into the PR description:

```yaml
release:
  kind: patch
  note: "Signing methods narrowed to what SmartLMS requires: a fix, not a new requirement."
```

The linter checks a version that is not in `releases.yaml` and the last one entered there: a release enters the version in the same PR. Older released versions are not checked after the fact.
