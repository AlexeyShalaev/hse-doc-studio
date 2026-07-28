---
title: What goes over the network
description: The exhaustive list of the Studio's network activity — and how to reduce it to zero.
tags:
  - Reference
  - Privacy
---

# What goes over the network

<p class="hds-lede">Local-first is a verifiable claim, not a slogan. Below is the complete list of cases where the Studio touches the network, what exactly is transmitted, and how to switch each one off.</p>

## Always local

The text of your work, metadata, change history, form answers, signature PNGs, built PDFs — **never leave the machine**, under any settings. LaTeX builds, GOST/ESPD and typography checks, LanguageTool, presentation conversion, the ONLYOFFICE editor — all run in local containers.

## What goes online and when

| When | Where | What is transmitted | How to switch off |
|---|---|---|---|
| Installing and updating images | GHCR, Docker Hub | image download requests | don't update; images download only on your command (apart from the Studio's own auto-update) |
| Update checks | the GitHub releases feed | a version is requested; nothing about you is sent | `HSE_STUDIO__UPDATE_FEED_URL=off` — fully offline; auto-update toggles off in About |
| **A cloud AI provider** (if configured) | the Anthropic / OpenAI / your compatible API | **the text fragments you send to the agent**, and files it reads with its tools | configure no provider — or use local Ollama: the text never leaves the machine |
| The font catalogue | Google Fonts | catalogue search queries; downloading a chosen font | use system fonts or device upload |
| “HSE staff” lookup | hse.ru | a name query against the public directory | fill the supervisor in by hand |

## What does not exist at all

- **No telemetry, no analytics, no crash reports.** No counters or beacons, neither on this site nor in the app.
- **No Studio accounts or tokens.** The only keys in the system are the AI provider keys you entered yourself; they live locally in `ai_providers.json` in your data folder and go nowhere except the corresponding API.

## Fully offline

A working recipe: install the Studio, let the first build download TeX Live, set `HSE_STUDIO__UPDATE_FEED_URL=off`, configure no providers (or run Ollama). After that there is no network activity at all — you can write your thesis on a train.

!!! note "The Docker socket"
    The Studio manages containers through the mounted `docker.sock` — administrator-level
    access **to your own machine**, the standard approach for tools of this class. It has
    nothing to do with the network, but it is worth knowing: see
    [the installation flags](../start/install.md).
