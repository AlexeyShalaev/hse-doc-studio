---
title: First project
description: From a fresh install to the first submission package — one end-to-end scenario in twelve steps.
tags:
  - First steps
  - Project
---

# First project

<p class="hds-lede">From a fresh install to the first submission package — on a live example: Alexey Shalaev, group БПИ222, Faculty of Computer Science, HSE University.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/wizard</span></div>
    <img src="../assets/shots/wizard.en.light.png#only-light" alt="Project wizard">
    <img src="../assets/shots/wizard.en.dark.png#only-dark" alt="Project wizard">
  </div>
  <figcaption>the new-project wizard: template, metadata, folder</figcaption>
</figure>


1. Open <http://localhost:17240> — the setup wizard asks for a work folder; any folder you back up works, e.g. `D:/study/hse`.
2. Confirm the choice — the Studio recreates its container with that folder (the connection drops for a few seconds) and opens the **Projects** screen.
3. Press **“New project”** and pick a pack and a work template — a thesis, for example.
4. Take the template version marked “default” — it is locked into the project at creation.
5. Choose the track and the language of the work — they define the document set.
6. Set the name, the project folder and the presentation format (pptx / reveal / beamer).
7. Author: **Alexey Shalaev**, group **БПИ222**, the topic of the work.
8. Supervisor: the **“HSE staff”** button finds them on hse.ru and fills in the position and degree without typos.
9. Check the summary and press **“Create project”** — nothing touches the disk before this moment.
10. Fill the <span class="hds-fill">\hseFill</span> fields in the visual editor — ++tab++ walks you through the unfilled ones.
11. Press **“Build all”** — the first run takes longer than usual (the TeX Live image, ≈ 9 GB, is downloading); after that a rebuild takes seconds.
12. Open the normcontrol **Findings** — and package the submission on the **Submission** tab.

## Next

- [Workbench overview](../workbench/index.md) — how the interface works.
- [Findings](../workbench/checks.md) — what is checked after every build.
- [Submission](../workbench/submit.md) — how the submission package is assembled.
