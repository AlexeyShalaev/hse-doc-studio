---
title: Checks and rules
description: How normcontrol works — the rule, families, engines, severities and deliberate exceptions.
tags:
  - Reference
  - Normcontrol
---

# Checks and rules

<p class="hds-lede">Normcontrol is rules declared by the pack and engines that enforce them. What gets checked is what actually built — the finished PDF, the build log and the source with the <code>\input</code> chain expanded — not guesses from the preamble.</p>

Rule
:   A single check with an identifier of the form `family/name` — for example, `gost-7.32-2017/page-margins`. A rule has a category, a default severity and an engine that enforces it.

Family
:   The origin of the requirement: GOST standards (ESPD, the research report), Russian typography, grammar and style, the template's content requirements. The identifier prefix always tells you “who demands this”.

Engine
:   A way of looking at the work: measuring the finished PDF (margins, fonts, pages), parsing the build log, analysing the source and the text, or external services such as LanguageTool.

Severity
:   How serious a finding is — error, warning or info. The default comes from the pack, and you override it [on a finding, a document or the whole project](../workbench/checks.md).

`% hse-noqa`
:   An exception comment in the source: “I am ignoring this finding deliberately.” It shows up in diffs — the decision stays documented.

The full rule list of your template lives in the app itself: the Findings panel shows every rule with its origin and severity.
