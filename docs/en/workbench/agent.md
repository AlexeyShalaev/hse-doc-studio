---
title: AI agent
description: An assistant with tools — reads the project, edits with confirmation, builds and fixes; cloud models or local Ollama.
tags:
  - Workbench
  - AI agent
---

# AI agent

<p class="hds-lede">The agent is not a chat to “talk to” — it is an assistant with tools: it reads project files, findings and the build log, edits text and rebuilds documents. Every write to disk is confirmed by you.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/documents/thesis</span></div>
    <img src="../assets/shots/agent.en.light.png#only-light" alt="Agent chat">
    <img src="../assets/shots/agent.en.dark.png#only-dark" alt="Agent chat">
  </div>
  <figcaption>the agent docked next to the document, aware of the project</figcaption>
</figure>


It opens with the title-bar button or ++ctrl+j++; on a project screen it knows the project's context.

## What it does

- **“Fix with AI”** on a failed build — reads the log, edits the `.tex`, rebuilds.
- **“Fix with AI”** on a finding — a targeted edit for that specific issue.
- **“Ask AI”** about selected text in the PDF — “rephrase”, “shorten”, “check the logic”.
- **Free-form tasks** — “replace straight quotes with guillemets in chapter 2”, “build all documents and tell me what's wrong”.
- **Confirmations** — edits are never applied silently: “Apply” / “Reject” with a diff; auto-approve is a deliberate opt-in.
- **Personas** — built-in (style editor, strict normcontroller…) and your own, with their own instructions.
- **Models** — cloud providers (Anthropic, OpenAI and compatible) or local **Ollama**: the Studio downloads the engine and picks a model for your hardware — the text of your work never leaves the computer.

Chat history is searchable; for odd behaviour there is a run event feed with tool calls.
