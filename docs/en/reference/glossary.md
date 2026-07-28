---
title: Glossary
description: The Studio's vocabulary — interface and documentation terms in one place, strictly in the app's own wording.
tags:
  - Reference
  - Glossary
---

# Glossary

<p class="hds-lede">Terms as the interface uses them. If this site spells something differently than the app does — that is the site's bug: report it.</p>

## Templates and structure

Pack
:   A template bundle for an institution or a programme. The pack declares documents, metadata fields, check rules, forms and submission profiles.

Template
:   A kind of academic work inside a pack — a graduation thesis or a course project, for instance.

Version
:   A snapshot of the template's requirements. Locked into the project at creation — requirements do not shift mid-year.

Track (applied / research)
:   The work format. Changes the document set: which documents exist on each track is declared by the template.

Metadata
:   Project fields declared by the pack: topic, group, supervisor, code… Stamped into every document at every build. “Required for submission” — must be filled before packaging.

Project
:   A plain folder on disk with document files and the service `.hse-studio/` folder.

Slug
:   The short folder name of an author in a team project (`shalaev`).

Shared documents / `shared/`
:   Team-wide editions of documents next to the authors' personal sets.

## Documents and building

Document
:   One deliverable of the set. A document has a code, a status, its files and its build history.

Build / Build all
:   Compile one document (LaTeX → PDF) / queue the whole set.

Preview
:   The built PDF (or HTML slides).

Side-by-side
:   Preview + editor on one screen.

Code / Visual
:   Editor modes: raw LaTeX or the visual mode with rendered formulas and block cards.

Custom document
:   Your own file placed where a generated document would be (“Replace with your own file…”).

From template — protected
:   A pack-managed file: cannot be renamed or deleted; content updates from metadata.

SyncTeX
:   The PDF ↔ source link: Ctrl+click jumps both ways.

## Checks

Findings
:   Check results and build errors — the panel and the document tab.

Checks
:   The normcontrol machinery: engines + rules from the pack.

Rule
:   A single check with an id like `gost-7.32-2017/page-margins`; see [Checks and rules](checks-rules.md).

Severity
:   Error / warning / info. Overridable per finding, per document or per project.

Compliance: N%
:   The share of passed checks for a document.

`% hse-noqa`
:   The exception comment: “I deliberately ignore this finding” — visible in diffs.

## Submission

Submission
:   The rail mode covering everything needed to hand work in.

Checkpoint
:   A submission point — a [profile](checkpoints.md) declared by the pack: the package contents, signatures, forms.

Readiness ring
:   The “N of M ready” indicator on a checkpoint.

Package
:   Assemble the submission archive with canonical file names.

Submission build
:   One produced archive; kept under “Past builds”.

Form
:   A pack-declared questionnaire — an AI-use declaration, for instance; an official document builds from the answers.

Signature slot
:   A named signature placeholder (author, supervisor) with one PNG per project and per-document placement.

Requirements traceability
:   The “requirement → where referenced” matrix built from `\req` / `\reqref`.

## History and system

History
:   The project's git history in `.hse-studio/git/` — separate, not your repository: autosaves, named versions, diffs, safe rollback.

Important version
:   A named snapshot (“Chapter 3 done”).

Image
:   A Docker image of a managed service: TeX Live, LanguageTool, Gotenberg, ONLYOFFICE, Ollama.

Provider
:   A cloud AI connection (Anthropic / OpenAI / compatible).

Local models
:   Studio-managed Ollama — models on your own machine.

Agent persona
:   An instruction-persona for the agent; built-in and your own.

Run mode
:   How the Studio is installed: all-in-one (container) / separate containers / local run.
