---
title: Introduction to the Studio
description: Questions, an interface tour and a demo project in a sandbox. How to take, skip and restart it.
tags:
  - Getting started
---

# Introduction to the Studio

<p class="hds-lede">On first sign-in the Studio offers a short introduction: a couple of questions, a tour of the home screen and a demo project that shows the whole workflow. About three minutes, nothing real is created.</p>

## What is inside

1. **Questions** (three or four): who you are (student, supervisor, administrator), what you are working on (options come from the installed templates), experience with LaTeX and git. Any question can be skipped. The answers decide which steps to show and which template to suggest at the end.
2. **Home screen tour**: new project, the list and search, the AI agent, settings, the Help menu. Server administrators also see the way into the admin area.
3. **Demo project in a sandbox** (`/onboarding/demo`): creating a project from a template, editing, building and previewing the PDF, asking the AI agent, comments and git sync. Everything is simulated in the browser tab, so the demo works even where no build runners or AI provider are set up yet.
4. **Wrap-up**: “Create a project” opens the wizard with the template already selected. If cloud builds may be unavailable on the server, the Studio says so.

## Controls

| Action | How |
|---|---|
| Next and back | buttons in the hint or the → and ← keys |
| Skip | “Skip”, the cross or Esc |
| Do a step for you | the main button of a demo step (“Build”, “Sync” and so on) |
| Take it again | the Help menu (question mark, top right) or the “Introduction to the Studio” card in the profile or account settings |
| Demo project only | Help → Demo project |

Progress is saved in your profile: per user on a server, in the data folder (`onboarding.json`) in the local Studio. People who used the Studio before the introduction existed do not get the tour automatically: a dismissible invitation appears in the bottom right corner instead.

!!! tip "Recording videos"
    `/onboarding/demo?autoplay=1` plays the demo scenario by itself, with no clicks.
