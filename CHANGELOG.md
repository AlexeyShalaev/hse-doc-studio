# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.45.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.45.0...v0.45.1) (2026-11-27)


### Bug Fixes

* **pack-studio:** версия принятого запроса не называется черновиком до обновления пространства ([6fefd28](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6fefd289625445825a452c2c51fece327c2bee6a))
* **pack-studio:** версия принятого запроса не называется черновиком до обновления пространства ([0bbf463](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0bbf463a8f295cddafd50ccfb8fed27e36e9d533))

## [0.45.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.44.0...v0.45.0) - 2026-11-27

- Packs: in the BSc Software Engineering course project (hse-cs-se 2026.3.0) the co-supervisor's line on the approval sheets now has a signature place: personal and shared statement of work and test program, explanatory note, source listing, programmer's and operator's manuals. The signing order is unchanged: only the authors sign in the course project. This is a new version line, existing projects do not move to it by themselves.
- English teams: an author's folder and signatures are now named after the surname (Ivan Ivanov gives ivanov, not ivan). This applies to new projects and new members; existing authors keep their folder names.
- Pack Studio over MCP: pack_help has a section on a line for every author in a team project; the linter no longer warns about author anchors set through macros; signature boxes in the placement check carry the author's name; pack_submission can show a single submission point; a truncated file list now says so; scenarios can check that a signature is optional and accept the full version id; if_match is accepted without quotes; splitting a file into language editions no longer counts as a removal.

## [0.44.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.43.0...v0.44.0) - 2026-11-26

- Packs: team projects in the BSc Software Engineering thesis and course project (hse-cs-se 2026.2.0). On the team's shared documents (shared SoW, shared test program and methodology, shared annotation) each author has their own line and their own signature place. The approval sheet of a shared document fits on one page with three authors and with two authors and a co-supervisor. The practice supervisor's review has a co-supervisor line when a co-supervisor is set in the project; their signature in the route is optional and can be skipped. English documents no longer print Russian words on the approval sheet, the thesis and annotation title pages, in the hints of the shared SoW and in the list of manuals. A typo on the practice report title page is fixed. Existing projects do not move to the new version by themselves; the template update is offered as usual.
- File names in English projects: an author's personal document is now named after the surname, as in Russian projects (it used to carry the first name). The same rule applies to the submission package, the result in Pack Studio and detached signature files. Russian projects are unchanged.
- Pack Studio over MCP: pack_git_branch with from_base: true creates the working branch from the fresh base branch, which is handy after the previous proposal is merged; pack_preview_build with the author parameter builds the personal documents of any team member, not only the first one; pack_submission shows the signing routes in the text view too; in the signature places model the author__<slug> anchor comes with its slot and the author's name.

## [0.43.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.42.0...v0.43.0) - 2026-11-26

- Packs: signing routes in the BSc Software Engineering thesis and course project (hse-cs-se 2026.1.5). At every submission point with signatures, Send for signing offers a ready order right away: the student, then the co-supervisor (only when set), then the HSE supervisor; the academic supervisor does not sign. In the course project only the author signs, at the final upload. In a team project all authors sign the first step. Signature places on the title pages of the thesis, annotation, thesis report, course project report and on the approval sheets no longer cover the captions under the lines, in the Russian and English layouts.
- Packs: a group course project in the MSc System and Software Engineering (hse-cs-sse 2026.2.0). Each group member has their own project proposal, topic application, report and slides, as well as their own title and UDC; the proposal, the application and the report introduction name the group project and the other members, and the introduction has a place for the personal contribution. The Topic application route: all authors sign their applications, then the supervisor and the co-supervisor, then the academic supervisor (when the supervisor is not from HSE). On the report title page the signature boxes no longer overlap the date. Existing projects do not move to the new version by themselves; the template update is offered as usual.
- Team signatures: on shared documents (for example a shared SoW or test program) each author can have their own signature and date place. The template puts an author__<slug> anchor on the author's line; pack places, the route, rebuilds, Restore the template place and, in MCP, pack_signature_check and pack_signature_render work with each author's place. Older templates behave as before. How to turn it on in your pack is described in the pack format reference, section Team project: a line for every author.

## [0.42.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.41.0...v0.42.0) - 2026-11-24

- Runners: after a system update the admin area offers to update all runners together. On Admin, Updates, once the server runs the new version, an Update runners to vX dialog opens with the outdated runners (name, kind, current and new version), checkboxes and an Update all or Update selected button. Runners are updated one at a time, idle ones first; a runner with a build in progress waits for it for up to 15 minutes, the build is never cut off, and if it does not finish the runner is skipped. Progress and the result are shown in the same dialog, one runner's failure does not stop the others, and a run can be stopped after the current runner. Runners Studio cannot safely update (Helm, docker run outside the admin area, a service without saved SSH) are listed as Update manually with a hint. After Not now the dialog does not come back for the same version, and the banner on the Runners page stays as the manual route.
- MCP: tools admin_runner_fleet (outdated runners and the progress of a run), admin_runner_fleet_upgrade (update all or selected runners, dangerous) and admin_runner_fleet_cancel. Every action is written to the audit log.

## [0.41.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.40.1...v0.41.0) - 2026-11-24

- Packs: hse-cs-sse coursework 2026.1.8. The author's and the supervisor's signature places on the report title page are moved so the boxes no longer cover the Full name and Grade captions. Checked by an agent on a real build: 0 errors and 0 warnings. The text of the documents is unchanged.
- Packs: hse-cs-se VKR and coursework 2026.1.4. English hints for the title, short title, field of study, academic supervisor and document code fields (and UDC for VKR). The template files are the same as in 2026.1.3.
- Packs: the Co-supervisor role has one name in hse-cs-se 2026.1.4 and hse-cs-sse 2026.1.8, in the settings and in the list of signatures. Released versions are unchanged.

## [0.40.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.40.0...v0.40.1) - 2026-11-24

- Pack Studio: Refresh base now also works in a space without a work branch. With no unsaved edits the space moves to the latest master by itself; with edits, the files are left alone and the space card shows a clear error with a hint. After a background refresh the interface reloads the files by itself instead of showing stale ones.
- Pack Studio: the list of changed files is computed from the point where the space diverged from master, as in a GitHub PR. Files that merely appeared in the new master no longer look deleted, and the number of changes is the same on every screen and in MCP.
- MCP: a single tool call waits at most 50 seconds (preview build, git sync, cloning a cloud project). For long operations start them and wait with repeated calls; a larger value is accepted and capped at 50 seconds.

## [0.40.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.39.0...v0.40.0) - 2026-11-23

- Access tokens: the permissions of an existing token can be changed. In the account settings a token has an Edit permissions button: the same checkboxes as on creation and a summary of what is added and removed. The token itself stays the same and the new permissions apply from the next request; after changing MCP permissions, reconnect the AI client so it sees the new tools. Permissions can only be changed from a browser session, a token cannot raise its own rights, and every change is written to the audit log.
- Packs: signature places sit on the template's signature lines. In hse-cs-se VKR 2026.1.3 and coursework 2026.1.3 signature places are bound to the signature lines of the approval sheets, title pages and PDP forms; before, boxes could land on text or on each other. hse-cs-sse coursework 2026.1.7 adds the supervisor's signature and date place on the report title page. The text of the documents is unchanged.
- Pack Studio fixes after an end-to-end check: version comparison always opens with its styles; Why and Not included name conditions the same way as the For which student strip; What changed shows document names instead of ids; the what-changed line counts the rows visible on screen; the number of changed files and of remarks is the same on every screen; when access is refused, sending offers Repository access; Check, the official templates dialog and the workspace list use fewer technical words. On phones Esc closes the details sheet and the send button in Changes is no longer squeezed.
- Interface: the app consistently addresses the user formally in Russian, the co-supervisor has one name everywhere, coloured labels meet WCAG AA contrast in the light and dark themes, on touch screens every button is at least 44 px, notifications no longer cover the buttons of dialogs and side panels, and closing a dialog returns focus to the button that opened it.
- MCP: the signature place check no longer mistakes a date blank for a signature line, suggests a place even when no clean one exists, and marks a line the template does not print for this data as a hint rather than an error.

## [0.39.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.38.0...v0.39.0) - 2026-11-22

- Pack Studio: the new interface is now the only one and opens right away, without ?ux in the address. The old view (Files, the former Result, Matrix and Atlas) is removed, and old links lead to the right screen of the new interface. The Changes panel again has the Move edits to a new version button for a released version that was edited outside the Studio.
- Pack Studio: after describing the changes, releasing or renumbering, the main button shows the next step right away instead of asking to describe the changes again. In a narrow column the document title in Content is no longer covered by the buttons.
- MCP: Pack Studio can be run by an agent end to end. New tools: pack_changes (status of the edits and the next step with the tool that does it), pack_checks (check rules), pack_version_number (version number), a dry run for creating a version, cancelling a preview build. Pack check findings use the same words as the Check tab by default.
- MCP: signature places can be set by an agent. pack_signature_render draws the preview pages with signature boxes and returns them as images, pack_signature_check checks each place (on the page, not over text, not over another signature, next to its own signature line) and suggests fixes that are applied with pack_set_placement.

## [0.38.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.37.0...v0.38.0) - 2026-11-22

- Pack Studio: a new interface rebuilt from scratch. Instead of many switches, a space has three tabs, Result, Content and Check, one main button for the next step and a Changes button with the status of your edits. On entry the version with your edits opens first, then the last visited one, then the default version.
- New interface, Result: a For which student strip replaces the inputs panel. The centre shows the parts of the result with a table of contents, a Not included block with reasons and a highlight of what changed after picking another student. The Details panel explains in sentences why an element is the way it is and shows what changes if a condition changes. A condition is edited in place, with a list of edits and undo.
- New interface, Content: navigation over the documents and sections of a version, the document text with autosave and a jump to the nearest finding, the document signatures and a Signatures and places section, the version parts and All files. The PDF can be previewed as it will be built for the chosen student. The Edit a copy button is the same everywhere.
- New interface, Check: pack findings in plain words, typical cases with a case window (expectations, Accept, delete, the student view, filters, sorting and on screen now), What affects what and version comparison. Everything useful from the former Matrix and Atlas moved here.
- The new interface on phones and tablets: bottom tabs with a badge for the number of edits, sheets instead of side panels, large touch targets.
- Server texts (linter findings, build errors, changes in a comparison) are now shown in the Studio in plain wording. The Template Studio admin page is rewritten in plain language, with a setup checklist and a clear list of template sources. The glossary, the help and the site documentation use the new names.
- Pack manifests are parsed faster, so the server starts faster.

## [0.37.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.36.0...v0.37.0) - 2026-11-20

- Admin: the Update button now shows the progress of an update. A step by step indicator (version check, image pull, image check, stop, migrations, restart and rollout, health check), with the time and details of each step. While the application restarts, the previous progress stays on screen with a waiting message, and the result is shown on its own once the server is back.
- Admin: when an update fails, the reason is shown in plain language (image not pulled or not found by tag, no rights on the cluster, rollout did not finish in time, migration or health check failed and others), a What to do hint, a Details for support block with copying and a Retry the update button. If the executor is lost, it says so: the status is unknown. The update history shows who pressed the button, the duration and the outcome, and the confirmation screen shows the release notes. Tokens, addresses and paths are removed from the event texts.
- Template Studio: the top bar of the Result screen has two linked lists instead of one common list: first the pack, then a template of the selected pack. The default version is chosen automatically, and a pack change resets the scenario and the inputs.
- Template Studio: a result linter and rule coverage by scenarios. The Result screen has a new Pack check tab: findings by severity and rule with a How to fix hint, a jump to the rule and to the combination, a Check Jinja templates button and a Coverage block with an Add scenarios hint. The number of errors and warnings is shown in the top bar. 22 rules find slots that never reach the route in any combination, steps without a person, route gaps, conditions on missing fields and values, missing translations and silent Jinja render failures. pack check validates scenario files.
- MCP: every action of the Template Studio is available to AI agents. New tools: workspaces (create, delete, refresh the base, official packs), the file tree, a targeted YAML edit by JSON Pointer with conflict protection, deleting and moving files, the version model, hints, the document library, submission points and routes, scenarios (list, write, delete, run), the atlas, Why, the matrix, the result linter, git step by step (branches, commit, diff, checks, update from the base, start over), and the pack_help catalog with the typical order of actions. Access tokens are never passed through MCP, destructive actions need confirm, and sending a PR is still off by default.
- Fixed: fetching missing files in Official packs workspaces worked only when git named the missing object. It now also runs when git prints a single transport 'https' not allowed line, as happens on older git versions. Also fixed: writing the model server env file without an explicit encoding, and tests for Windows.

## [0.36.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.35.0...v0.36.0) - 2026-11-17

- Template Studio: edit a rule right on the Result screen. In the Why panel every chain item has Edit rule: kinds of work, staffing, languages, NDA, optional flags, questionnaire and signature slot conditions, disabled checks. After saving you see what changed in the result (plus, tilde, minus), Ctrl+Z and Ctrl+Shift+Z undo and redo edits, and a deleted record can be restored within 10 seconds. A released version is immutable, for it the button leads to the new version wizard.
- Template Studio: Matrix, Atlas and Compare modes. The matrix shows scenarios by result section with a status for every cell, including against the base. The atlas lists all distinguishable outcomes of a version, choosing a row applies those inputs. Compare shows the delta of two scenarios, two sets of inputs or two states (work tree, last commit, base) with reasons and a jump to the rule.
- Template Studio: Propose changes shows what will change in the result. A Result will change in N of M scenarios block with counters by section and an expandable list of changes. If scenarios changed or failed, you tick I know the result of these scenarios will change, but sending is never blocked. A short summary goes into the PR description. The Result screen now has a Propose button.
- Template Studio: scenarios on screen. The scenario picker shows the run status of each one, Save as scenario builds assertions from the current result, you can accept the current result as expected, duplicate and delete with a 10 second undo. The PDF preview opens right from a result document, with a choice of document variant and scenario, and auto build is toggled by a switch.
- Template Studio: As a student mode shows three simplified blocks (which documents the student gets, what to fill in, who signs in what order) without service marks, Alt temporarily brings back the author view. Missing elements are shown pale with the reason and an Add in inputs button. The Result screen was rebuilt for phones: a compact top bar, a Parameters sheet, Inputs, Result and Why tabs, and unified bottom sheets.
- MCP: the pack_outcome_compare and pack_outcome_impact tools compare the result of two sides and count in how many scenarios the result changes against the base. pack_preview_build accepts variant and scenario.

## [0.35.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.34.1...v0.35.0) - 2026-11-16

- Template Studio: a new Result screen opens by default. Pick the language, kind of work, authors, supervisors and other inputs and see right away what you get: documents with final file names, project metadata fields (visible and required), expected participants, submission points, the signing route with its steps, checks, variants and edition languages. The choice lives in the page address, so a link can be shared. The previous screen with the file tree is still available as the Files mode.
- Template Studio: every result element has a Why panel. It shows the chain of rules (held, not held, skipped) with the condition in words and the actual values, neighbouring elements and What if: which change of one input would change this element, applied with a click. Open the rule leads to the exact record in the form or to the line in the source, and Back to result returns you to the same place. For an input you can see how many elements and sections it affects.
- Template Studio: the Inputs panel is built from the version schema (switches, lists, number of authors, supervisor role, pack fields, questionnaire answers, document variants), marks what was changed and resets values. The Not affecting block lists inputs that change nothing for the current choice.
- Template Studio: scenarios are stored in the pack itself next to the examples. A scenario is a named set of inputs with an expected result (a snapshot and assertions) and can be run on the work tree, the last commit and the base. Starter scenarios were added to the official packs. The atlas shows all distinguishable outcomes of a version (for example, 864 rows and 384 outcomes for a thesis) and the impact analysis of inputs. For now scenarios and the atlas are available through the API and MCP, screens for them come in the next release.
- MCP: the pack_outcome_inputs and pack_outcome tools give agents what the Result screen shows: the dictionary of inputs and the result for a set of inputs, in three states (work tree, last commit, base), in a compact text form or in full, with a scenario argument. They need the packs token scope and the Template author right.

## [0.34.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.34.0...v0.34.1) - 2026-11-16

- Fixed: an Official packs workspace showed "Could not read the local repository copy" right after creation. Git looked for .gitignore and .gitattributes rules outside the packs folder, and their files were missing in the partial clone. The workspace now fetches the needed files with its token, and existing workspaces repair themselves when opened.
- Template Studio: when git fails, the banner shows collapsed support details with the command and the error line, without URLs or server paths.

## [0.34.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.33.0...v0.34.0) - 2026-11-15

- Files: upload your own files into a project from the browser. Upload files and Upload folder buttons, folder menu items and drag and drop from the computer into the tree. On a name clash you can replace, keep both or skip. Progress is shown, one file is up to 50 MiB.
- Files: an image opens in Files, a PDF in the viewer, anything else is downloaded. Uploaded PDFs (figures, scans) now go into history and git sync, only built PDFs are excluded.
- Fixed: the preview said the document was never compiled when the build succeeded but checks found errors. The preview now shows the PDF with a note, and the status reads Check errors instead of build error. A failure of the checks themselves no longer loses the built PDF.
- Fixed: the git tab of a Template Studio workspace failed with a 502 "transport 'https' not allowed" after the base was updated. The state is computed without downloading files, missing files for a diff are fetched with the workspace token, and git errors are shown as a clear message.

## [0.33.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.32.0...v0.33.0) - 2026-11-15

- Template Studio: a Form tab for version.yaml and doc.yaml. Fields and groups, questionnaires, documents, languages and translations, and variants are edited with the mouse, no hand-written YAML. A field preview and where it is printed are shown alongside. YAML comments and order are kept, and an edit that breaks the pack is not saved.
- Template Studio: forms for submission checkpoints and the signing route (items, submission methods, signature slots with conditions and optional ones) and a "Route in this combination" block showing the route for the selected preview switches.
- Template Studio: forms for checks and rules, and running the checks on the preview with findings shown next to each rule.
- Template Studio: New pack and New template, from scratch with the Minimal scaffold (a GOST 7.32 report) or as a copy of an existing version with new ids.
- MCP: pack_* tools for the Template Studio: reading and editing pack files, checks, preview, signature places, the new version wizard, creating a pack and a template, git and Propose changes. They need the packs token scope and the Template author right; sending a PR is off by default and needs confirmation.

## [0.32.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.31.0...v0.32.0) - 2026-11-15

- A GitHub token can now be pasted right where it is needed: in the Official packs dialog, in New workspace of the Template Studio and in Git access (the Add token button). The Studio checks the token and selects it right away. The hint for official packs suggests a classic token with the public_repo scope.
- Packs: a fast packs check in CI and the hse-doc-studio pack ci init command, which adds a ready CI (GitHub Actions or GitLab CI) to your own packs repository.
- Docs: a new Template Studio section for pack authors and an article on where a pack in the project wizard comes from.
- Fixed: in local mode with the texlive TL2024-historic image the first xelatex build failed without a format. The missing format is now built automatically and kept in the cache.

## [0.31.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.30.0...v0.31.0) - 2026-11-15

- Pack catalogs: an administrator connects packs from a git repository or an archive in the new admin section "Pack catalogs". The Studio checks the packs and shows a plan (new, changed and incompatible versions); after "Apply" they appear in the project wizard without a restart. Once a day the Studio picks up newly released versions on its own.
- Template Studio: signature places and dates are now placed with the mouse right on the preview PDF.
- Template Studio can run on your own machine: a docker compose profile in deploy/pack-studio or make pack-studio. It opens your packs folder and hides projects.
- Official packs: changes can be proposed only with your own GitHub account, through your fork. The service bot was removed for security, together with its daily limit and admin settings.

## [0.30.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.29.0...v0.30.0) - 2026-11-15

- Fixed: notification emails (signature requests, "Everyone has signed" and others) were not sent and showed up in the mail log with an InterfaceError. Now an email is sent after the action is saved, and not at all if the action was rolled back.
- Template Studio: Official packs. A separate button opens the packs of the main HSE Doc Studio repository, and changes go out as a PR. Use your own GitHub token or no account at all: the installation's bot sends changes from its own fork. The bot path is limited to the packs folder, a daily proposal limit, license consent and audit records. Bot setup is described in the docs.
- Template Studio: New version wizard. A copy of a released version, the version class (patch, minor, major) with reasons on every edit, a number based on the class, version notes with a draft, and release into releases.yaml.
- Template Studio: PR CI status now shows when checks are waiting for a maintainer's approval, and after merge says when the version reaches users.
- Fixed: template preview occasionally showed "build interrupted" for a build that had actually finished.

## [0.29.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.28.0...v0.29.0) - 2026-11-15

- Template Studio: a new /pack-studio section for template authors. A server-side working copy of the pack repository, a file tree, an editor with completion for form fields and \hse macros, and a Problems panel that checks the pack as you type. Administrators grant access with the Template author right.
- Template Studio, git: branches, Save version, one-click Propose changes (pack checks, push, a GitHub PR or GitLab MR), pushing to a fork when you lack rights, CI status, a diff view, Pull main branch and Start over. Administrators can add a service access to the repository so authors do not need their own tokens.
- Template Studio, preview: build a PDF of a template version from its examples or from automatic data sets (normal, long, empty) with chosen switches, plus the build log and cancel.
- Command line for template authors: hse-doc-studio pack lint, check, classify, new-version and freeze, with JSON output.
- Templates: fixed labels cut off at a comma inside the text (for example "Monospace font (code, listings)"). New versions: hse-cs-sse coursework 2026.1.6, hse-cs-se coursework and thesis 2026.1.2, internship 2026.1.1. The PDF does not change. The pack linter now catches this.
- Settings, AI clients (MCP): the tool list no longer overflows, and the command field has no extra empty line.
- Security: dnspython updated to 2.9.2 (CVE-2026-128089).

## [0.28.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.27.0...v0.28.0) - 2026-11-14

- Mail log, version 2. Mail the mail server rejected temporarily is resent by the Studio itself: up to 5 attempts after 1, 5, 15 and 30 minutes. The log shows which messages are still being retried and which failed for good. A message has a “Send again” button, and the log has “Send unsent”. Self-diagnostics gains an “Email delivery” check that warns when mail stops going out.
- Runner disk autoclean. When a shared runner has less than 10% of disk left, it cleans the build cache by itself, at most once an hour. The threshold and the switch are in the runner row in the admin panel, along with the result of the last cleanup. Requires runner 0.28.0. After an update the updater removes images of versions older than the previous one, so rolling back one version stays fast.
- Template security: Jinja in packs runs in a sandbox. A template cannot reach Python internals or server files. The output of our packs is byte for byte the same. The pack linter also catches symbolic links, token-like strings and the -shell-escape flag.
- For template authors (first steps of the Template Studio). The linter works out the class of a new pack version (patch, minor, major) from the changes and does not allow releasing it softer than needed; the reason goes into release.note. JSON schemas for pack manifests are published (contracts/pack), so hints and validation work right in the editor.
- Fixed random failures of signing route e2e tests caused by the login rate limit.

## [0.27.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.26.0...v0.27.0) - 2026-11-14

- Signature places on template lines. A template can mark a signature or date line in LaTeX (an anchor), and after a build the box lands exactly on it. Places follow the layout by themselves: the document language, lines printed by a condition and a long title. The mark reads “Place on a template line”, and when the line is missing from the document the place is turned off. Places set by hand, documents out for signing or with an e-signature and an uploaded PDF never move. After a build the Studio tells how many places it moved.
- MSc course project template 2026.1.5: a ready route for the topic application. The author, then the supervisor and the consultant (when set), and the academic supervisor only when the supervisor is not from HSE. Signature boxes and dates sit on the lines of the application and the project description, and the author's signature and date on the report title. Checkpoints now hint when the deadline is usually announced. The PDF does not change after updating from 2026.1.4, so documents out for signing do not get “Has changes”.
- Builds are now reproducible: XeLaTeX no longer writes the build minute into the PDF. Before, a document without hyperref rebuilt without changes in another minute came out different, and a document out for signing could get a false “Has changes”. The fix is in the runner: update runners to 0.27.0 in the admin panel. On an older runner template lines are not detected and places come from the fallback millimetres.
- Times in emails, reminders, invitations and the AI limit message are now in Moscow time, for example “15 Nov 2026, 23:59 (Moscow time)”. The checkpoint deadline reminder has a signing line: who we are waiting for, finished or not sent. Consecutive date mark edits by one person are merged into one route history event.

## [0.26.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.25.1...v0.26.0) - 2026-11-13

- Checkpoint deadlines. Each submission checkpoint in a project can have a deadline, date and time in Moscow time. The template does not set it, it only hints when it is usually announced. The checkpoint shows “in N days”, “today”, “package built” or “overdue”, and the project list marks the nearest deadline. MCP reads it and sets it with set_checkpoint_deadline.
- The signing route deadline is now set automatically, one day before the checkpoint deadline, to leave time to build the package. Three days before the checkpoint deadline the owner and authors get a reminder in the Inbox and by email, unless the package is already built.
- Route from the template. A template can define the route steps for a checkpoint, extra signatures with a condition (for example, the academic supervisor only when the supervisor is not from HSE), optional signatures, and signature places and date marks for each document. A new route draft is built from this preset. The editor shows “from the template” and “Changed by you” marks and offers “Reset to template” and “Reset place to template”. The template never touches places you set by hand or routes already sent. Ready routes for the course project come with the next template version.
- A template update moves “from the template” signature places to the new version. Places set by hand, documents out for signing and signed documents stay as they were, and the preview shows what will and will not change. Undoing the update restores the places.
- MSc course project template 2026.1.4. City and year in the documents come from the project: the year in the application and signing dates is the build year in Moscow and can be overridden, and the city is translated on the English page. The topic application is printed as one page in the project language. The consultant line appears only when a consultant is set, and the academic supervisor's consent line only when the supervisor is not from HSE. The supervisor switch is now called “HSE / Not from HSE”. In the bachelor templates 2026.1.1 the city on English title pages also comes from the project.
- MCP connection guides for Codex, OpenCode, Gemini CLI, Windsurf, Zed, Cline and JetBrains Junie. The “AI clients (MCP)” page lets you pick a client and shows its ready config, taking the token from the HSE_STUDIO_TOKEN environment variable where the client supports it.
- For template authors: the Signatures tab “⋯” menu has “Copy as template preset”. It produces a ready YAML fragment with signature places and date marks for the template.

## [0.25.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.25.0...v0.25.1) - 2026-11-13

- A document replaced with your own PDF showed as not built on the send for signing page, and signatures and freezing used the wrong file. The signature plan, the route, freezing and the pack now use the uploaded PDF. Studio doesn't see a signature drawn inside the uploaded PDF: upload the signature as an image into the slot.

## [0.25.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.24.0...v0.25.0) - 2026-11-13

- Signing date. A signature slot can now have date marks: “Add date” on the Signatures tab or in the “Where signatures go” block of the route editor. A mark can sit on any page, apart from the signature. Formats: day, month as a word, month as a number, year, two-digit year, and the full date in numbers or words.
- The date in a mark is the moment the signer approved on the route, in Moscow time, for both an image and an e-signature. If the person approved before the marks were added, the date is taken from that approval automatically. Outside a route the author sets the day in the “Signing date” field. A skipped signer gets no date. On the signing page the signer's own frames are labelled “Approval date”.
- Date marks can be added on a running or finished route without stopping it. If an e-signature already stands over the document, the Studio first warns whose signatures will be reset. After you confirm, the document is frozen again and those people get a new request to sign the final PDF. HOW_TO_VERIFY.txt gains the lines “date on the page” and “signing time”.
- Fixed: the date inside a signature frame used UTC, so a night-time approval in Moscow printed the previous day. A double full stop after initials in the signature reset warning. A new mark near the right edge of the sheet no longer goes past the page edge.
- Building a document with date marks needs runner 0.25.0 or newer. Update runners in the admin panel, Runners section.

## [0.24.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.23.0...v0.24.0) - 2026-11-13

- Optional signatures and skipping a signer. For each signature slot on a checkpoint the author can tick “Signature is optional”, even on a route that is already running. When it is the turn of a signer whose signatures are all optional, the author presses “Skip” and the route goes on without a restart and without losing approvals.
- A skipped signer gets a “signature not required” notice and email, and the event is recorded in the audit log. If an e-signature already stands over the document, the skipped signer's mark stays, otherwise the document is frozen again without it. A skipped signer can be brought back by sending a new version. MCP can read this but not skip.
- The submission pack is not blocked by a skipped or optional signature, and HOW_TO_VERIFY.txt lists it as not required. While a route is not finished the pack cannot be built, and instead of an English 400 error the Project folder card explains why: the route step and who we are waiting for.
- Comments from the PDF preview. The selection bar has a new “Comment” button. A comment is anchored to the LaTeX source through SyncTeX, or to the place on the PDF page when the source is not found or there is none. Margin marks and a Comments panel show them, also on phones. On servers with runners SyncTeX now comes back with the PDF, so “In source” and Ctrl+click work.
- Registration: exemptions from admin approval. In the sign-in settings you can list addresses and domains (hse.ru, *.hse.ru, name@example.com) that do not need approval. The exemption applies only to a confirmed address: after the email or on single sign-on. The “Check address” line shows the result before saving, and a pass by rule is written to the audit log.
- The double dot after initials (“Petrov P. P..”) is fixed on the signing page, the route card and elsewhere. The signing page is lighter: rare dialogs load only when opened.
- On phones the document tab row scrolls with an edge hint, the selected tab scrolls into view, and the “…” button stays on screen.

## [0.23.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.22.0...v0.23.0) - 2026-11-11

- New admin section “Mail”: every email the Studio sent or tried to send, with its outcome (sent, failed, not sent), recipient, subject and who triggered it. Filters by kind, outcome, recipient, project and period, plus search.
- The “Last 24 hours” band and the menu counter show how many emails failed; on a sign-in, connection or TLS failure a hint links to the mail settings. If mail is not configured, the section says so plainly.
- The email card shows the message as the recipient saw it. Token links (password reset, confirmation, invitation) and people's messages are not stored in the log and are hidden in the preview. Failures show the class, the SMTP code and “What you can do”.
- Emails no longer disappear silently: if the recipient's address is unverified, sign-in is closed or SMTP is not configured, the log keeps a row with the reason. The SMTP login and password are hidden in error texts.
- The log is kept for 90 days; the period is set in Data retention and is part of “Free up space”. Deleting a person erases emails to them, and their data export lists them.
- MCP: a new read-only admin_list_mail_log tool for administrators.
- Admin help gains a “Mail” article. The docs no longer promise a mail queue: each email is attempted once and its outcome is in the log.

## [0.22.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.21.1...v0.22.0) - 2026-11-11

- Runner disk in the admin: the runner menu shows how much space Studio images, the build cache and the runner cache take and what can be freed. Clean block by block or with “Clean all”; the current and previous versions and volumes are never touched. Progress and the result show right in the window.
- The runner performs the cleanup itself from its own fresh measurement; the server sends only the target, never image names. The disk view needs runner 0.22.0 or newer; older runners show a hint to update.
- Kubernetes runners show and clean only their own cache: node images are removed by Kubernetes itself. The local Studio as a runner points to the Disk section in its settings.
- My runners: owners see the disk of their runner and may also remove the previous version. If an admin cleaned a personal runner, the owner gets an inbox notice; an admin cannot remove the previous version on someone else's runner.
- Storage: the “Free up space” button runs all retention cleanups at once. Before the run you see how many records each source will lose, after it how many were removed and how much disk was freed. The run happens on the server and survives a closed tab. Next to it, “Where else to free space” lists runners.
- Every cleanup is recorded in the audit log. Admin help gains a “Runner disk” section and a “Storage and space” article, user help gains “My runners: disk”.
- The “⋯” menu on phones no longer picks an item with the same tap that opened it.
- The project creation wizard shows its steps as a left column on wide windows again.

## [0.21.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.21.0...v0.21.1) - 2026-11-11

- Admin, Runners: the update button of an outdated runner no longer overlaps the Status column. A compact “v0.21.1” button sits under the version, with the full “Update to v0.21.1” label in the tooltip.

## [0.21.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.20.1...v0.21.0) - 2026-11-11

- The signing route signs the version taken at send, the “version on signature”. Edits and rebuilds no longer stop the route: signers see and sign exactly the PDF that was sent.
- The first edit, file upload, build or office editor launch on a document out for signing asks a soft question instead of blocking: you can go ahead and the route keeps going.
- “Send new version” sends the fresh build: approvals on unchanged documents are kept, only changed documents are approved again, and only people whose approval was dropped are notified.
- The Signatures tab, the route card, the editor banner, the inbox and the signer page show the date of the version on signature and warn when the current build differs from it.
- The submission pack is built from the signed version; if a document changed after sending, the pack and HOW_TO_VERIFY.txt carry a warning. Dates in it use Moscow time.
- While a document is on a route, signing the current build outside the route is closed; cancelling the route releases the version on signature.
- Routes started before the update are migrated automatically: the build that already has approvals becomes the version on signature. If it cannot be found, the route offers “Send new version”.
- MCP: get_signing_route shows the versions on signature and changed documents, edits via MCP return a note about the route, and a new version is sent only from the UI.
- The signing route docs and in-app help are updated for the version on signature, with fresh screenshots.

## [0.20.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.20.0...v0.20.1) - 2026-11-10

- The signing route shows both stages: “1 of 3 approved · 0 of 3 signed” on the card and “1/3 approved” in the checkpoint header. An e-signature waiting for the freeze is marked “approved, signature after freeze”.
- An old detached signature for an earlier PDF of a document on a route is no longer shown as a red “Invalid”: a neutral note explains that the route will ask to sign again.
- Slot frame labels on the PDF preview no longer overlap in narrow frames.

## [0.20.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.19.0...v0.20.0) - 2026-11-10

- The signing route explains what it is waiting for. “Sign the set”, the “Signing” card and the signing page say who approves now, who has not accepted the invitation yet and when the Studio will ask for your e-signature. People who have not accepted get a “Copy link” button.
- The “Waiting for your signature” counters no longer count signatures that are on a signing route and agree with each other. The card shows names from the project card instead of masked emails and counts required and optional signatures separately. A document on a route no longer shows a false “Signatures are invalid” warning or freeze buttons.
- A build is no longer marked outdated after signature actions or after building another document: freshness depends only on sources and title data.
- If a signature image or plate cannot be placed, freezing, “With signatures”, packages and routes stop with a clear error and no PDF without the mark is created. Stamping works with pypdf 7.
- Gender-neutral Russian texts in notifications, emails and the interface; “checkpoint” is used consistently.
- The PDF toolbar fits on phones: paging and zoom stay visible, the rest is in the “⋯” menu, search opens as its own row.
- Docs: screenshots for “Send for signing” and “How to sign”, in-app help articles for the route screens. Dependencies updated.

## [0.19.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.18.0...v0.19.0) - 2026-11-10

- Signing route “Send for signing”. The author prepares a route on a checkpoint: who signs, in which order, where the signatures go on the pages, a deadline and a message. Signers get the request in the Inbox (and by email if the server has mail set up) and sign on their own page with an image (draw, upload or use a saved one) or an e-signature (a Studio key, CryptoPro in the browser, or a ready signature file). A key can be created or imported right there.
- The order is kept: the next person gets the request after the previous one approves. A signature image goes into the PDF only after approval, and e-signatures come last over the frozen PDF, so a later signature never breaks earlier ones. The PDF is frozen automatically.
- If a document changes, the route stops and the author sends it again; approving again takes one click. A signer can return the documents for revision with a comment. While a route runs, the signatures of its documents cannot be changed.
- The “Signing” card on a checkpoint shows the route progress, “Remind” and “Copy link” for each signer (useful while the server has no mail). The Inbox has a new “To sign” tab and the bell counts these tasks. Reminders go out automatically a day before the deadline and after three days of waiting.
- Signer profile in settings: a saved signature image and a public key or certificate for the plate. The server never accepts private keys.
- Reproducible builds: rebuilding LaTeX without changes gives a byte-identical PDF, so signatures and routes are not reset by it.
- MCP: get_signing_route and list_signing_tasks show route progress and your tasks; the dangerous send_for_signing sends for signing. Approving and signing over MCP is not possible. Route actions appear in the audit log.
- Docs: new pages “Send for signing” and “How to sign”. The scheduler leader probe no longer confuses locks from other databases on the same Postgres.

## [0.18.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.17.2...v0.18.0) - 2026-11-09

- «Signed» download returns the actual signed file. If the PDF is frozen and current, you get it as is, with PAdES signatures when there are any. Without a current freeze you get a print copy with visible stamps but no electronic signatures. Signatures are no longer applied anew on every download.
- With PAdES signatures the signing package holds two PDFs: the final signed one and the original for detached signatures, named as in the LMS package.
- Moving a project folder or switching between the local Studio and the cloud no longer makes signatures outdated: the visible layer fingerprint uses paths inside the project. Existing signatures stay valid.
- SSE coursework template 2026.1.3: at topic approval and final submission signatures are accepted as an image or a detached signature, not PAdES. Existing projects get it as a template update; a slot already set to PAdES asks to change the method.
- MCP create_project creates team projects: several authors, supervisor, co-supervisor and academic supervisor with the same checks as the creation wizard. list_templates shows whether a template supports teams, and set_project_people accepts an author topic.
- The local Studio on macOS gets its document fonts: the installer copies Times New Roman, Arial, Courier New and Consolas from the Mac, since Docker Desktop cannot mount the system fonts folder. If fonts are missing, settings explain why.
- The SSH install dialog on the model servers page no longer shows raw keys instead of text.

## [0.17.2](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.17.1...v0.17.2) - 2026-11-09

- Cloud builds in a separate namespace work again: a build pod no longer gets the runner pod from another namespace as its owner, which made Kubernetes delete it at once and the build failed with a Kubernetes executor error. This affects runner.installFromUi.buildNamespace and runner.kubernetes.namespace.
- A detached OpenPGP signature made with a Studio key is now verified on cloud runners too: the Studio passes the signer's public key to the runner. Previously such a signature showed as an unknown signer key and a signer mismatch. The secret part of the key never leaves the server.
- OpenPGP keys follow the server key storage policy: when storage is forbidden they cannot be created or imported, and stored keys cannot be used to sign, the same as .p12 certificates. Public keys for checking other people's signatures can always be uploaded. The Keys on the server counter in the admin area counts OpenPGP keys, and a secret key disguised as a public one no longer gets into the keyring.
- An OpenPGP key and its passphrase are passed to gpg without temporary files on disk.

## [0.17.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.17.0...v0.17.1) - 2026-11-09

- A successful build without output files no longer stays unfinished: previously its result was not applied and the api retried it on every restart.

## [0.17.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.16.0...v0.17.0) - 2026-11-09

- Signatures by plan: a document has a signature plan (who signs, where and how), and the submission point counts readiness from it. Methods can be mixed in one document: a signature image, an image with a digital signature, an invisible digital signature, a detached signature. Sign bundle signs all your slots in the submission point documents in one step, PAdES is applied over the frozen PDF, and slot permissions are checked.
- The LMS bundle is built from the signature plan. MCP gains get_signature_plan and sign_submission: signing over MCP needs a separate sign permission on the token, a password-protected key is not used over MCP, and passwords and keys never appear in responses.
- MCP is extended: template update (status, plan, apply), document variant selection, project fields and clearing them, editing one author, the author e-mail and the academic supervisor, project members, invitations by e-mail and access revocation, and git_sync as the sync button with a summary and a list of conflicts. All changes go through the same permissions and audit log as the web interface. compile_document and clone_cloud_project wait up to 45 s so they stay within the client timeout.
- Inviting a supervisor or co-author opens with a ready message built from the project data: name, topic, role. The text can be edited before sending.
- Build queue: documents that no runner can take are not queued by Build all and are listed separately, and busy runners are told apart from missing ones. In the admin queue, the jobs of one Build all are grouped into one row that can be cancelled as a whole.
- Cloud builds survive an api restart: jobs are not lost during a rollout, the server stops gracefully, and a build interrupted by a restart is shown as interrupted instead of hanging. The api downtime window during a rollout is shorter.
- Admin-installed runners: a separate namespace for build pods (runner.installFromUi.buildNamespace), a built-in Gotenberg for office jobs (pptx, docx) with its address passed to runners, and office jobs on the isolation screen. Removing an install revokes the runner, a failed update rolls back to the previous version, and the admin area shows whether the runner came back online.
- Templates: the Studio knows the inventory of built-in packs and recognises a mounted template catalog. If the catalog is behind, the message names it instead of suggesting a Studio update, and updating warns about it. The pack binding of a dev build is no longer carried over to the published image.
- Fixes: placeholders in disabled edition branches (\if) no longer count in checks; the ⋯ menu and tooltips on desktop are clickable again over the settings dialog.

## [0.16.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.15.0...v0.16.0) - 2026-11-08

- In-place update of admin-installed runners: a runner installed from the admin area in Kubernetes or Docker is updated to the Studio version without removing and reinstalling it. The name, token, data volume and install limits are kept, the manifest is applied with the current isolation rules, progress is shown step by step, and the update is written to the audit log. The chart adds the update permission on Deployments.
- Admin-installed runners are managed on the Runners page: Update and Remove install in the Actions menu, an Update to vX button for outdated runners, and a separate block for installs whose runner is already revoked.
- The local Studio no longer offers to fetch cloud builds of documents that are not produced as PDF (such as pptx), and build fetch failures now show specific messages instead of a generic connection error.

## [0.15.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.14.0...v0.15.0) - 2026-11-08

- Runner details in the admin area: where each runner runs (Kubernetes pod, container or host) and how it builds documents (Docker or Kubernetes), its CPU, memory and storage limits, and a cluster isolation panel. The panel shows the policies declared in Helm and, with runner.isolationInfo.readCluster enabled, what actually exists in the cluster: NetworkPolicy, ResourceQuota, LimitRange and Pod Security labels.
- MCP: create_project no longer asks for a folder in the cloud, the new set_project_people tool sets the project supervisor and members (recorded in the audit log), and clone_cloud_project in the local Studio clones a project from the cloud.
- Kubernetes builds no longer fail with idle_timeout after the PDF is ready: word and character counting is time limited, and if it hangs the build still succeeds with a warning.
- Local Studio linked to the cloud: the server version is refreshed on sync, a last build id that this Studio does not have is no longer returned, and documents without a PDF (such as pptx) no longer fail PDF autopublish.
- SPI coursework template 2026.1.2: the topic application matches the official 2026 form, names are shown as "Surname I.O.". The released 2026.1.1 is unchanged.

## [0.14.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.13.0...v0.14.0) - 2026-11-07

- Roll back to an earlier version from the admin area: a list of published releases, each with a verdict on database schema compatibility. A rollback is allowed only to a version with the same migration state, a backup is taken first when configured, and if the version does not come up the system returns to the previous image. Requires an updated updater.
- Auto-install switch for updates: while it is off, new versions are not installed on their own, but checks and notifications continue. After a successful rollback auto-install switches to notify-only mode. Rollbacks and toggles are written to the audit log.
- Limits and isolation for Kubernetes runners: requests and limits for CPU, memory and storage on runners and build pods (set in Helm and in the install form in the UI), clear failure reasons for out-of-memory and storage overruns, deny-all network traffic for build pods, optional runner egress policies, ResourceQuota and LimitRange, stricter pod security settings and reduced Studio permissions. Already installed runners stay unchanged until reinstalled.

## [0.13.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.12.0...v0.13.0) - 2026-11-07

- Model servers: the admin area has a new Model servers page. It installs Ollama, vLLM or SGLang on the machine that runs Studio, or on another one over SSH (one-time password or key, with an offer to save the access encrypted). It shows the API address and key. By default a server listens on the loopback interface only; vLLM and SGLang are exposed publicly only with an API key and after confirmation. For gated models a Hugging Face token is set in settings. In Helm, installing on the same machine is off by default (modelServers.local.enabled).

## [0.12.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.11.0...v0.12.0) - 2026-11-07

- Installing a runner with a single command: creating a token now shows a ready docker run line and a script that installs the runner as a service (systemd on Linux, launchd on macOS). The script contains no secrets and supports a dry run, status and uninstall.
- Installing a runner on the same machine as Studio from the admin area: as a container in Docker, or as a separate restricted Deployment in Kubernetes (off by default in Helm, value runner.installFromUi.enabled).
- Installing a runner on other machines over SSH from the admin area: host key fingerprint confirmation, password or key with passphrase, a plan and step-by-step progress. Credentials are one-time by default; you can optionally save them encrypted for updates and reinstalls. Internal networks stay blocked until the address is added to HSE_STUDIO__RUNNER_INSTALL__SSH_ALLOWLIST.
- For administrators: the server applies the new migration on first start (ri_01_runner_ssh_credentials), no manual steps are needed. SSH installation requires asyncssh (included in the server build).

## [0.11.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.10.0...v0.11.0) - 2026-11-06

- "Build all" no longer leaves jobs queued forever when the personal runner is busy and there are no shared runners: jobs wait for a free slot on the personal runner. Jobs that are already stuck are picked up on the runner's next poll.
- Self-diagnostics: every problem row can be opened to reach the page where it is fixed, for example a queue failure leads to the runners queue tab and backups lead to the backups page.
- Settings, Disk: Studio offers to clean up old system versions (images of earlier versions, stale tags of helper images, the stopped updater). The latest previous version kept for rollback is protected from bulk cleanup.

## [0.10.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.9.0...v0.10.0) - 2026-11-06

- A stale tab after an update no longer breaks the admin area: the app picks up the new version and offers to reload the page.
- The build queue shows real phases (queued, building), and the "Build is not responding" warning counts from the actual start, not from the click.
- Stopping a build in the cloud is synced with the local Studio and back: the status updates in both places.
- Warnings about missing backups and public runners can be acknowledged on purpose, and they stop nagging.
- The documents panel and the agent chat no longer overflow at narrow widths and large text sizes: buttons, labels and the model picker fit.

## [0.9.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.8.0...v0.9.0) - 2026-11-05

- The topic application and the presentation build without supervisor or author data: the new course project template version 2026.1.1 fixes the There's no line here to end error that broke the build when a signature field was empty. New projects are created on it right away, existing ones see it as a recommended small update: accept it in the project settings
- Cloud builds on a personal runner get the same fonts as local builds: Times New Roman, Arial and Consolas, which the local Studio takes from your computer when the runner connects if the fonts folder is empty. For a shared runner and a runner in Kubernetes the fonts folder is set by a setting (a volume). Microsoft fonts are not shipped with the Studio or its images. If a template asks for a font directly and it is missing, the build fails with a clear font missing reason and the font name
- Fixed a false upload error: when Build all started several builds of one project, the second build could delete the first one's finished PDF and the first reported that the result could not be uploaded. The result is now copied aside before uploading, and if the file really is missing the reason is named PDF not received. A failed build also no longer shows an endless Build is not responding warning and the Stop build button
- Text size: the step you pick no longer snaps back to the account value. Before, choosing 100 % right after 140 % could roll back until the save reached the server. Now an explicit choice on the device always beats the account value and is saved to the account, retrying on error
- For administrators, upgrading from 0.8.0: no database migrations. New runner settings: HSE_RUNNER__FONTS_DIR, HSE_RUNNER__FONTS_HOST_DIR and HSE_RUNNER__FONTS_MOUNT_TARGET (Docker runner), HSE_RUNNER__K8S__FONTS_CLAIM and runner.kubernetes.fonts.existingClaim in Helm (Kubernetes runner). Template 2026.1.1 is used automatically for new projects

## [0.8.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.7.0...v0.8.0) - 2026-11-04

- Text size: in Settings, Appearance you can choose the interface text size (90, 100, 112, 125 or 140 %). It changes at once across the whole app (menus, forms, dialogs, the editor, the admin area, the landing page), is remembered in your account and applies without flicker on load. Document content and the PDF page are not scaled. On a phone the 90 % step does not shrink buttons and fields below a comfortable size
- A failed build explains itself: the Build tab shows the failure code and reason, what to do and a Build again button, and the document list and the Now block show the reason under the name. The build log now reaches the cloud (before it was empty even for successful builds), including live, and refusals before start (no Docker, TeX image or runner) are recorded as a failed build. Reasons are named in plain words: no output for too long, no disk space, the result could not be uploaded to storage and others. The build silence timeout is raised from 120 to 300 seconds: the first build on a fresh font cache can stay quiet for a long time
- Presentations and other office documents in the cloud through your Studio: if Docker runs on your computer and the Gotenberg image is pulled (docker pull gotenberg/gotenberg:8), the local Studio tells the cloud it can convert, and the Build button for presentations and Word documents is no longer blocked. Without Docker or the image the previous explanatory message stays
- For administrators, upgrading from 0.7.0: the release has one database migration (cf_01_compile_failure, two optional columns in the build record), the server applies it itself on first start, take a backup before updating. New settings: HSE_STUDIO__COMPILE__IDLE_TIMEOUT_S (300 seconds by default) and HSE_RUNNER__TEX_IDLE_TIMEOUT_S for the runner. Runner build logs are kept on the api volume (meant for a single api replica)

## [0.7.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.6.0...v0.7.0) - 2026-11-04

- Mobile cloud version: the Studio is comfortable on a phone from 360 px. Dialogs and menus open as bottom sheets, tables become cards, input fields no longer zoom the page in iOS, buttons are at least 40 px, and the screen notch and on-screen keyboard are accounted for. Sign-in, the landing page, the home screen with the project list and filters, the inbox and Studio connection all work
- The project workspace on a phone: a bottom bar of sections (documents, remarks, submission, files, more), a project header with people online, connected Studios and sync, an editor with a scrollable toolbar and a distraction-free mode while typing, a PDF with zoom by buttons and pinch, and the agent chat full screen. Settings and the admin area also work well on a phone: sections in a sheet, single-column forms and tables as cards
- Not yet working on a phone: the ONLYOFFICE editor, side-by-side mode, keyboard shortcuts (the command palette and help are in the account menu), drag-and-drop of files into the window, CryptoPro signing and the onboarding tour with highlights. Tablets keep the desktop layout. The mobile version was tested on emulation, please report anything you find on real devices
- Fixes: the Help window opened from the account menu crashed on a phone; the Signatures and Authors pages of a project were clipped on narrow screens
- For administrators, upgrading from 0.6.0: this release has no database migrations and no new required settings, only the interface changes

## [0.6.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.5.0...v0.6.0) - 2026-11-04

- Cloud landing page: someone who opens the server address and is not signed in sees a page describing the Studio (who it is for, what it does, how to start, security) with the sign-in form right on it. The link to the cloud can be shared: messengers show it with a title, a description and a picture. Invitations, password reset, OIDC and passkey sign-in work as before. An administrator can turn the landing off in the installation settings, then the sign-in page opens straight away
- Connected Studios: a cloud project shows which of your local Studios are connected, whether they are online (or when they last were), the version, project sync, PDF upload, the state of your personal runner and of AI through your machine. The local Studio shows the same the other way round: the link to the cloud, what the cloud sees, who else is online in the project. For each document you can see where and when it was built and whether the build is current. A cloud PDF can be fetched into the local Studio with the Get build button, and with automatic sync on it is fetched by itself. The cloud has a My Studios list with a Forget device button. Only state metadata is sent: no paths, contents or keys
- People in the project: the project header shows avatars of members who are online right now, with a caption of what and where they are doing (editing the Application, viewing remarks, working locally) and a jump to the same document. Another person's cursor in a document shows their name, and the cursor colour matches their avatar. Members see each other in the browser and in the local Studio, guests with an access link are not listed. The load is minimal: one light signal a minute per person, nothing written to the database
- Bell and settings: the bell opens a small window with the latest notifications, a mark-as-read action and a Show all link instead of going to a page. The settings window is taller and wider, its menu scrolls and section names no longer wrap. When a local Studio cannot use AI through its runner, the reason and what to do are now shown, and the cloud has an Add in the cloud button for the Through my runner provider
- For administrators, runners outside the server network and storage: personal runners and browsers get S3 links at a public address. Set it with s3.publicEndpoint in Helm (HSE_STUDIO__S3__PUBLIC_ENDPOINT); the storage has to be published under its own name with TLS (see the runners section). Without a public address a cloud build on a runner outside the network fails with a clear storage_unreachable error and the self-diagnostics page warns. A fallback without publishing the storage: s3.outsideRunnerAccess: proxy, results go through the server
- For administrators, upgrading from 0.5.0: the release has one database migration (cd_01_connected_devices, connected devices and build data), the server applies it itself on first start, take a backup before updating. New settings: s3.publicEndpoint, s3.outsideRunnerAccess, s3.sharedRunnersOutside (Helm), HSE_STUDIO__SERVER__LANDING_ENABLED and the landing switch in the admin area. Fixed: for a cloud project the open repository button led to a 404 page, now it opens the project page

## [0.5.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.4.0...v0.5.0) - 2026-11-03

- Cloud projects in the local Studio: once connected to a server, the local Studio lists your cloud projects itself, in the same list as local ones and marked Cloud. One click on Open downloads the project into the projects folder (changeable in settings), shows the progress and opens it, with no clone wizard and no git on this path. The Open in local Studio link from the cloud takes you straight to the right project. Automatic sync and PDF upload need no setup and work for cloud projects from the start. If an open project is not linked to the cloud, the build panel says so: the PDF will stay on this computer
- Nicer e-mails: invitations, e-mail confirmation, password reset, address change, passkey notifications and project access e-mails now arrive designed, with a large button, a fallback link, a note on why you received it and a security block, along with a plain-text version. An e-mail is written in the recipient's account language (Russian or English) and the subject is translated too. In the admin area (Sign-in and registration) you can preview every e-mail in both languages and send a test one
- For administrators, one-button updates in Kubernetes: on the Updates page the Update and Roll back buttons now work in a cluster too. Turn it on with the updater.enabled flag in the Helm chart (off by default) and HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes: a separate pod changes the api Deployment image, runs migrations as a Job and waits for health, and the image is checked against the digest from the release. Permissions are limited to its own namespace. A backup runs first if one is configured, otherwise you must confirm the risk. If migrations were applied but the new version did not come up, the image is not rolled back automatically: the status is Needs hands, with ready commands. After such an update set the version in your values (image.tag), otherwise the next helm upgrade will bring the old image back
- Fixes: in the dark theme the answer options in the welcome questionnaire were black on dark and unreadable; the settings sidebar did not scroll, so lower sections (such as AI clients (MCP)) were out of reach, and the AI group heading was shown twice; on the server every start logged a local Ollama sync error
- For administrators, upgrading from 0.4.0: there are no database migrations in this release, the schema stays at pk_01_passkeys. New settings: updater.enabled in Helm (off by default), HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes, and for the local Studio the cloud projects folder (Settings, Repository access). E-mails are sent as HTML together with a plain-text version: without SMTP nothing changes and links are still shown on screen

## [0.4.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.3.0...v0.4.0) - 2026-11-03

- Passkey sign-in: sign in with a fingerprint, Face ID or a hardware key instead of a password. Keys are added and removed in the profile, sensitive actions ask you to confirm your identity again, and an admin can reset a person's keys. An invitation to a specific address lets the person create an account with a key right away, with no password; an e-mail is sent when a key is added or reset. The admin people list shows the number of keys
- MCP: AI clients (Claude, Cursor and others) work with the Studio over the Model Context Protocol, both in the cloud at /mcp and in the local Studio on localhost. 51 actions are available: projects, files, builds, checks and the norm-control report, requirements, review comments and history. It works with a personal token carrying the MCP permission; dangerous actions are off by default, an admin turns each one on or off in the installation settings, and e-signatures are not available over MCP. For a local client there is the hse-doc-studio mcp bridge. See the AI clients (MCP) section for setup
- In-app help: articles with screenshots and short videos in Russian and English, in light and dark themes. Onboarding for new people: a short questionnaire and a guided tour that highlights interface elements on a demo project (creating a project, editing, AI, git) without risking your data; it can be run again
- Local version from the cloud: the server has a Local version page explaining how to download and install the local Studio and connect it to this server; installers run with HSE_STUDIO_CONNECT open the connection screen straight away. The server is checked before connecting
- Builds without runners: instead of a 503 error the Studio plainly says there are no cloud runners, blocks the build buttons and suggests building the document locally. The same applies when no runner has the required tags
- For administrators, runners in Kubernetes: in the Helm chart runner.executor=kubernetes starts a pod per build in its own namespace (permissions on pods only, with a NetworkPolicy), so the node's docker.sock is not needed. The default is still docker
- For administrators, upgrading from 0.3.0: the server applies the new migrations on first start (ob_01_user_onboarding, pk_01_passkeys), no manual steps are needed. New settings: passkey sign-in (admin → Sign-in, or HSE_STUDIO__AUTH__PASSKEYS_ENABLED; HSE_STUDIO__AUTH__PASSKEY_RP_ID for a shared parent domain of keys) and MCP (admin, off by default). If you change the server address public_url, existing passkeys stop working

## [0.3.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.2.0...v0.3.0) - 2026-11-02

- Shared server: teams can use the Studio together. Accounts and organisations, role-based project access, an installation admin area (/admin: people, sign-in and OIDC, mail, runners, queue, audit), builds on runners in isolated containers. Deploy with Docker Compose or Helm, see the Shared server section of the docs
- Collaboration: access links with a role, expiry, password and guest sign-in; invitations by e-mail or login, access requests and project ownership transfer; reviewers comment on the text and several people edit one document at the same time, seeing each other's cursors
- The Studio server as a git remote: the local Studio signs in to the server with a device code (device flow), sees the server's projects and clones and syncs them over git via HTTPS. Projects can be moved from the local Studio to the server together with their data
- Local Studio: automatic project sync with the server (on by default for projects obtained by signing in to a server, can be turned off per project) and PDF upload after a successful build, so supervisors and reviewers see the result without building
- Personal runners and AI providers: attach your own machine as a runner with a pairing code and build documents on it; the AI agent can work through your runner while your keys stay with you. Cloud builds on this machine are available right from the local Studio
- Quotas, AI gateway and runner autoscaling: limits on storage, builds per month, AI tokens per day and month and project members (installation default, organisation, user); when exhausted, choose low priority (default), reject or warn. The AI gateway records calls and fails over to another provider. The runner count can follow the queue automatically (webhook, compose or KEDA metrics); off by default
- Data autonomy: everything that grows has a retention period and background cleanup (audit 365 days, AI log 90, build logs 30 and so on; adjust them on the Data retention admin page). Audit and AI logs are split into monthly partitions, container logs are rotated, and when a disk reaches 90% a safe mode rejects large uploads while everything else keeps working
- Backups: schedule, full backup of the database, files and objects, server-side encryption, S3 or directory destinations (your own MinIO via one compose overlay), a connection test and failure alerts. Restore from the admin area with a preview, confirmation and maintenance mode, or with the hse-doc-studio backup restore command
- Self-diagnostics: the Self-diagnostics admin page checks the database, migrations, storage, disk, runners, queue, scheduler, TLS, backups and mail, explains the cause and suggests what to do; it alerts only on persistent problems. hse_diag_* metrics and a public /health/diagnostics
- Automatic server updates: release check every 6 hours, install by button or automatically in a maintenance window, backup and database snapshot first, image digest and cosign signature verification, automatic rollback if the new version does not come up. Default mode: notify only
- For administrators, upgrading: 0.2.0 was local-only, so there are no server installs on it and no database migration from 0.2.0 is needed: the server applies the whole chain on first start, from 0001 to dg_01_diagnostics (the latest being lc_02_partition_logs, bk_01_backups, up_01_server_updates, dg_01_diagnostics). Local 0.2.0 installs update with the Update button or update.sh / update.ps1 and their data is untouched. The server auto-updater installs only releases that ship an image-digest.json, i.e. 0.3.0 and later: it cannot install anything older, and when the digest is missing the run is cancelled (digest_missing) unless verification is set to None
- For administrators, environment and images: MinIO in compose is replaced with the pgsty/minio fork (web console restored, tag pinned); set S3_ACCESS_KEY and S3_SECRET_KEY, and keep SECRETS_KEY safe, since it encrypts secrets and backups. Auto-update is enabled by the updater profile: UPDATER_TOKEN in .env and docker compose --profile updater up -d (the service gets the docker socket, so it is off by default). New variables: HSE_STUDIO__SERVER_UPDATE__*, HSE_STUDIO__BACKUPS__*, HSE_STUDIO__LIFECYCLE__*, LOG_MAX_SIZE and LOG_MAX_FILE; see the variable reference for the full list. Off by default: automatic update installation (notify-only mode) and runner autoscaling; scheduled backups start working once a destination is added
- The code and tests run on Windows and macOS: fixed paths, directory permissions, encodings and network checks that broke running on those systems

## [0.2.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.3...v0.2.0) - 2026-10-26

- Master's programme: a 1st-year coursework template for System and Software Engineering — topic and application, report and slides
- Detached electronic signatures: freeze a PDF, sign it with an OpenPGP key or a qualified signature via the CryptoPro browser plug-in right in the Studio, or upload an existing signature. The Studio verifies it, adds an HSE-style signature stamp and builds the submission package
- Update a project to a new template version: project settings now have a Template version section. You see which files change before updating, your own edits are kept, conflicts are shown separately, and the update can be undone
- An available template update is flagged by a badge on Project settings, a dot in the outline, the status bar and a notification when you open the project
- A project saved by a newer Studio opens read-only, so an older version cannot accidentally damage its data
- New Topic and application document group, the academic supervisor's name fills the signature slot, and the Group field hint depends on the programme
- Dependencies and the base image updated, closing the vulnerabilities found in it

## [0.1.3](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.2...v0.1.3) - 2026-07-28

- The AI agent now works with any local model: if a model lacks tool support (e.g. phi3.5), it switches to a text protocol and keeps answering
- Agent errors are no longer lost — the failure reason shows up right in the chat
- Terminal updates: the update.sh and update.ps1 scripts run the same updater as the Update button — settings preserved, automatic rollback on failure
- Docs site polish: the banner always announces the current release; fixed the What's-new link, tab underline and buttons

## [0.1.2](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.1...v0.1.2) - 2026-07-28

- Fixed the app-error crash on the AI agent's very first reply (a duplicate router instance after a dependency update)
- The error screen now has a “Report an issue” button: it opens GitHub with the error, stack trace and version pre-filled — just add what you were doing

## [0.1.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.0...v0.1.1) - 2026-07-28

- The one-command install now also works in stock Windows PowerShell 5.1
- Install scripts speak English by default and Russian with HSE_STUDIO_LANG=ru; the docs pick the flag to match the page language
- A running local Ollama now registers itself as a provider — no more manual setup; the settings offer a one-click connect as well
- Every AI-agent tool is now translated in the tools menu: PDF reading, versions, projects, ask-the-user
- The data folder now ships with a ready-made projects directory — the project wizard suggests it right away

## 0.1.0 - 2026-07-28

- First release: a local studio for academic documents — projects from templates (thesis, coursework, Project Proposal) with every accompanying document and presentation
- One-click PDF builds: LaTeX runs inside a Docker container, nothing to install on your machine
- Code and visual editors with a built-in PDF viewer and text↔layout jumps (SyncTeX)
- GOST formatting checks: findings are anchored to source lines, many fix themselves automatically
- Submissions: the studio assembles the checkpoint package together with signatures and forms
- An AI assistant inside your project: bring your own provider (Claude, OpenAI and compatibles) or a local model via Ollama
- Project version history: timeline, diffs and restore — no git knowledge required
