---
title: Findings
description: Normcontrol before the normcontroller — GOST check findings, severities, rule management.
tags:
  - Workbench
  - Findings
  - Normcontrol
---

# Findings

<p class="hds-lede">After every build the Studio runs the document through its check engines: the ESPD GOSTs and GOST 7.32-2017, the template's rules, Russian typography, LanguageTool grammar. The result is Findings: concrete issues with line numbers and ways to fix them.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/documents/thesis?tab=checks</span></div>
    <img src="../assets/shots/checks.en.light.png#only-light" alt="Findings tab">
    <img src="../assets/shots/checks.en.dark.png#only-dark" alt="Findings tab">
  </div>
  <figcaption>Findings: the rule, the source line and the severity of each finding</figcaption>
</figure>


## What it does

- **A project-wide summary** in the Findings panel and a full breakdown on the document's tab — with filters and “Compliance: N%”.
- **A finding is a card**: the rule, the message, “Open in editor at line N”, “Fix with AI”.
- **Deliberate exceptions** — “Ignore this finding” (`% hse-noqa` on the line), “Ignore the rule in this document”, changing a finding's severity.
- **Severities** — error (almost certain to bounce off normcontrol), warning, info.
- **The rule catalogue** — enable and disable rules one by one or by category; project-wide opt-outs live in project settings.
- **What actually built is what gets checked** — the source, the log and the finished PDF: “left margin 25 mm instead of 30” means the page margins were measured.
- **LanguageTool runs locally** in its own container — your text goes nowhere; the rule language follows the work's language.

The rule set is declared by the template: a fresh project builds without a single “error” — findings speak about your text, not about the template. How rules and engines work — in the [reference](../reference/checks-rules.md).
