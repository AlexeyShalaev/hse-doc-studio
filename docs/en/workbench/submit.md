---
title: Submission and packaging
description: Checkpoints from the template, the readiness ring, forms, signatures and packaging archives with canonical names.
tags:
  - Workbench
  - Submission
  - Signatures
---

# Submission and packaging

<p class="hds-lede">Submission mode gathers everything needed to hand the work in: the checkpoints from the template, forms, signatures and packaging an archive with canonical file names.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/submit</span></div>
    <img src="../assets/shots/submit.en.light.png#only-light" alt="Checkpoint">
    <img src="../assets/shots/submit.en.dark.png#only-dark" alt="Checkpoint">
  </div>
  <figcaption>a checkpoint: the readiness ring, documents, signatures and forms</figcaption>
</figure>


## Checkpoints { #checkpoints }

A checkpoint is a package composition declared by the template: which documents, forms and signatures a particular submission needs. The reference calls it a submission profile.

- **The readiness ring** “N of M ready” on every checkpoint; once you “Pin” it, badges across the Workbench count blockers towards that checkpoint.
- **Item statuses** — “built”, “not built”, “with errors”, signed or not; “Open document” goes off to fix it.
- **“Package”** — an archive (zip, tar.gz and more) with canonical names: “Technical specification.pdf”, not `technical_specification.pdf`; preflight checks run before packaging.
- **“Past builds”** — package history: contents, “Download”, “Copy path”.

The checkpoints of each template are described in the [reference](../reference/checkpoints.md).

## Submission deadline { #deadline }

A checkpoint deadline is announced in the LMS and differs every year, so the template does not set it. You set it, for each checkpoint of your project. The template can only hint when it usually falls: the hint shows in grey under the deadline line, for example “Usually mid-November; the exact date is announced in SmartLMS”.

**Set the deadline.** While a checkpoint has no deadline, its page shows “No submission deadline” under the title, the template hint (if any) and the fields “Date” and “Time, Moscow” (23:59 by default). Click “Set deadline”. “Not now” hides the line for this checkpoint in this browser and leaves a “Set deadline” button instead. The pencil next to the deadline (“Change deadline”) changes it, “Remove deadline” removes it.

The project owner and editors set the deadline; everyone with access to the project sees it. A deadline in the past can be set too, for example to see “Overdue”.

**What the deadline line says.**

| State | Example | When |
|---|---|---|
| no deadline | “No submission deadline” | no deadline is set |
| ahead | “Due: 15.11, 23:59” | more than 3 days left |
| soon | “Due: 15.11, 23:59 (in 3 days)” | in 1 to 3 days |
| today | “Due today by 23:59” | the deadline is today and has not passed yet |
| package built | “Deadline passed 15.11: package built 14.11” | the deadline has passed and the checkpoint package was built in time |
| overdue | “Overdue: package not built” | the deadline has passed and there is no checkpoint package built in time |

Days are counted by the Moscow calendar: a deadline on 15.11 at 10:00 is “in 1 day” on the evening of 14.11, not “today”. Whether you uploaded the work to the LMS the Studio does not know. So “overdue” means exactly “the package was not built by the deadline”: what counts is this checkpoint's package built with “Package” within the 14 days before the deadline and no later than it.

**Project list.** A project shows a mark with its nearest deadline: “Topic application: in 3 days”, “…: today”, “…: overdue”. It shows the nearest deadline in the next 30 days, otherwise an overdue one no older than 7 days. A supervisor sees the same on the students' projects they are a member of.

**Reminder.** Three days before the checkpoint deadline the project owner and the authors (in a team project, every member with the author role) get a reminder in the Inbox and by email: “Due in 3 days: Course project topic application (SmartLMS)”. Supervisors do not get it: the signing route reminds them of the route deadline. If the checkpoint has a signing route, the reminder shows where it is: “Signing: waiting for the supervisor (name)”, “Signing: completed” or “Signing: not sent”. Times in the email are Moscow time: “15 Nov 2026, 23:59 (Moscow time)”. If the checkpoint package is already built for the deadline, there is no reminder. It comes once per deadline; if you change the deadline, a reminder about the new deadline comes again, three days before it. After the deadline there are no reminders: “Overdue” shows on the checkpoint and in the project list. The email goes out only if mail is set up on the server and your address is confirmed. A local Studio does not send reminders.

**Route deadline.** When you open “Send for signing”, the Studio sets the route deadline one day before the checkpoint deadline right away, so that a day is left for the package after the last signature ([Deadline and message](send-for-signing.md#prepare)).

**Where the deadline is stored.** In the project file `.hse-studio/project.json`, so it travels with the project to a local Studio, through git and on export. It does not affect builds: changing it does not make documents outdated and does not show “There are changes” on documents out for signing. In a team project there is one deadline for all authors. A local Studio shows and edits the deadline.

Over MCP, `list_submission_profiles` reads the deadline and `set_checkpoint_deadline` sets and removes it ([MCP](mcp.md)).

## Forms { #forms }

Forms are declared by the template — for example, an AI usage declaration. The Studio renders the form, shows a live preview and produces the official PDF from your answers; the status is visible in Submission and in the “Now” block.

## Signatures { #signatures }

!!! tip "Supervisors' signatures on a server"
    On a shared server you can [send the checkpoint's documents for signing](send-for-signing.md): the supervisors sign in turn on their own page. While the route is running, the signatures of its documents cannot be changed on the “Signatures” tab, and “Sign the submission” skips them with an “Open the signing page” link.

- **The signature library** — one PNG per slot (author, supervisor…) for the whole project; a built-in editor: “Remove background”, eraser, crop, ink colour.
- **Placement** — drag the signature to the right spot on the document page, with a date if needed.
- **Date marks**: “Add date” on a signature prints the signing day in frames of its own, anywhere in the document and in the format you need, for example «« 13 » ноября 2026 г.» with three marks. For a signature outside a route you set the day in the “Signing date” field; for a signature in a route the approval gives it. More: [Signing date](send-for-signing.md#dates).
- **Stamping** — when the PDF is frozen and packaged the PNG is stamped into it; there is a cryptographic layer too — a PAdES electronic signature with a certificate from Settings, appended to the frozen PDF.
- **“With signatures”** — if the document is frozen and unchanged since, the button returns the final file byte for byte, with embedded PAdES signatures if there are any. Otherwise it is a PDF for printing with images and plates, without electronic signatures.

### Detached electronic signature { #detached-signatures }

For documents signed with an enhanced electronic signature or through GnuPG (a topic application, a statement), a signature slot has a second type: “Detached e-signature”. Instead of a picture, the PDF carries the caption “Signed with a detached electronic signature”, and the signature itself is attached to the document as a separate file.

1. On the document's “Signatures” tab switch the slot to “Detached e-signature”, enable it and place the caption frame (with a date if you want).
2. **“Freeze PDF for signing”**: the Studio makes a copy of the PDF with the caption and shows its SHA-256. The signatures cover exactly those bytes. After the document is rebuilt the signatures are marked invalid and the freeze has to be repeated.
3. Attach a signature in one of three ways:
    - **upload a ready file**: `.asc` or `.sig` (OpenPGP) and `.sig` or `.p7s` (CMS/CAdES, including GOST R 34.10-2012 from CryptoARM and CryptoPro). The format is detected automatically; you can drop the file on the slot. The Studio shows the signer (name, CA, certificate validity, algorithm) and checks the signature against the frozen PDF. For OpenPGP with an unknown key it asks for the signer's public key;
    - **sign in the Studio**: with an OpenPGP key or a `.p12` certificate from “Settings → Signing certificates”. A key can be created right in the signing window, the name comes from the project. In the web version this works only if the administrator allows keys on the server (admin, “Signing keys”): otherwise a key cannot be created or uploaded, and keys already stored cannot sign. A signer's public key for checking a signature can be uploaded under any policy;
    - **send for signing**: “Files for the signer (zip)” holds the PDF, its SHA-256 and instructions; the supervisor returns the signature file. On a server it is easier to [send for signing](send-for-signing.md): the supervisor uploads the signature themselves.
4. The submission package gets the frozen PDF unchanged, one signature file per signer, the OpenPGP public keys and a README with verification commands. A package with such a slot is not built without an attached signature.

What is checked and what is not: file integrity and the signature itself (RSA, ECDSA, GOST R 34.10-2012 with Streebog, OpenPGP), the certificate validity at signing time. The chain to a CA root counts as trusted only after the root certificate is added in “Settings → Signing certificates”. Revocation lists (CRL, OCSP) are not checked. A qualified signature on a token cannot be made inside the Studio: sign the file in CryptoARM or CryptoPro and upload the result.


#### Token e-signature and the chain of trust { #cryptopro }

- **“Token e-signature”** on a slot opens a signing window that uses the CryptoPro Browser plug-in. Pick a certificate: the Studio takes the plate data from its public part, freezes the PDF again if needed, the plug-in signs the file on the token (CryptoPro asks for the PIN) and the signature is checked like any other. The private key never leaves the token. You need CryptoPro CSP, the plug-in and the browser extension for Chrome or Edge. The `cadesplugin_api.js` script comes from the CryptoPro site; offline, put it into the data folder: `cadesplugin/cadesplugin_api.js`.
- **“Complete the CA chain”** downloads the CA certificates linked from the signer's certificate. It is the only network request made while checking a signature, and only on your click. When the chain reaches a self-signed root the Studio shows its name and SHA-256: compare the fingerprint with an official source (e.g. e-trust.gosuslugi.ru) and click “Trust this root”. After that the chain counts as trusted.
- If the signer's certificate carries a CryptoPro class policy (KC1 and up), the plate level is set to “enhanced qualified”. It is a hint and can be changed.

## MSc SSE course project forms in 2026.1.4 { #forms-sse }

In template version 2026.1.4 of the MSc SSE course project (`hse-cs-sse`) the forms take data from the project rather than from the template. A project on 2026.1.3 gets this by updating from the project overview card.

- **City and year.** The “City, year” line of the application, the report title and the slides takes the city from the “City” field in the project settings (Moscow by default). English pages print Moscow, Saint Petersburg, Nizhny Novgorod and Perm in English and other cities as entered; another spelling goes into the “City in English” field.
- **Year in the application and signature dates.** The topic application and the date lines under signatures print the current year by Moscow time at build. The “Year in the application and signature dates” field sets it by hand: for example, the document was signed last year and is built again. The report title and the slides use the academic year from the “Academic year” field.
- **Application in the project language.** The topic application prints one page: Russian or English, by the project language. If you change the project language, the page changes on the next build.
- **Conditional lines.** “Consultant (if any)” is printed only when the project has a consultant (a full name is filled in). “Consent of the academic supervisor” is printed only when the supervisor is not from HSE. No line means no signature is needed either.
- **“HSE / Not HSE”.** The supervisor's switch in the project settings (the same in the creation wizard). “Not HSE” means a supervisor from a company or another university: then the application gets the academic supervisor consent line.

**Updating to 2026.1.4 while a route is running.** If the application is already out for signing, the update does not stop the route: the signers sign the version sent earlier, and the document shows “There are changes”. The update plan warns about this with an “Out for signing: …” line. To have the corrected form signed, click “Send new version” on the Signing card. The update does not change the route composition: if the supervisor is from HSE but the academic supervisor is on the route, their signature can be marked optional and skipped ([Optional signatures and skipping](send-for-signing.md#optional)).

## Requirements { #requirements }

The traceability matrix: every requirement from the specification (`\req{…}`) and where it is referenced (`\reqref{…}`) — the “covered / not referenced” statuses expose gaps before the committee finds them. The recognition format is configurable, and “Suggest with AI” proposes one from your text.

## Team projects

Submission computes readiness for one author at a time: pick whose package to build — the ring, blockers and archive recompute. Shared documents enter every author's package.
