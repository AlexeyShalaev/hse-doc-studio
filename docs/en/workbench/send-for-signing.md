---
title: Send for signing
description: How to send a checkpoint's documents to supervisors for signing in order on a shared server, follow the progress, send again after an edit and build the package.
tags:
  - Workbench
  - Submission
  - Signatures
---

# Send for signing

<p class="hds-lede">On a shared server you can send a checkpoint's documents to your supervisors for signing. The Studio keeps the order itself: each person gets a request in their turn and signs on their own page, and you see who has the documents now.</p>

## When to use it

When other people have to sign the checkpoint's documents: the supervisor, a co-supervisor, the academic supervisor. You do not have to explain to everyone where their signature goes or make sure the academic supervisor does not sign before the supervisor.

- It works only on a Studio server. A local Studio has no such button: sign your own slots with “Sign the submission” or send the supervisor the [files for signing](submit.md#detached-signatures).
- The project owner and editors can send. In a team project there is one route for the whole team, and the authors sign in parallel.
- Only a person signed in to their own account can sign. The link in the email opens nothing without signing in.

## How signing goes

1. You prepare the route: who signs, in what order and where the signatures go.
2. You click “Send for signing”.
3. The first person in line gets a request in the Inbox and by email. They open the signing page, look at the PDF and approve or sign.
4. The next step gets its request once the previous one is done. People in one step sign in parallel.
5. When all visible signatures are in place, the Studio freezes the final PDF, and those who sign with an electronic signature add it.
6. Everyone has signed: build the package.

What a signer sees is described in [How to sign](how-to-sign.md).

!!! note "Why electronic signatures come last"
    An electronic signature covers the exact bytes of the PDF. Signature images and the plates of electronic signatures are printed in that same PDF. If another image is added to a page after an electronic signature, the file changes and the signature already made becomes invalid. So first everyone approves the document in turn, and the visible signatures appear as they do. Then the Studio freezes the final PDF once, and electronic signatures go on that file. This way no signature breaks another.

## Invite the signers

A signer is a project member with the “Reviewer” role and a persona: “Supervisor”, “Co-supervisor” or “Academic supervisor”. The persona tells the Studio which signature slots are theirs.

- If the person is not in the project yet, the route shows “not in project” next to them and an “Invite” button. It opens the usual invitation form with the “Reviewer” role and the right persona already chosen: enter the email and click “Invite”. After accepting the invitation the person lands right on the signing page.
- You can also invite people in advance in the project settings, “People” section. More: [Invitations and access requests](../deploy/invitations.md).
- If several people have the persona, pick one in the “Who signs” list.
- You can send while an invitation is still pending: that person's step will wait.
- Inviting from the route needs the right to share the project: the owner or an editor with “Can share”. If registration on the server is closed, you can only invite people who already have an account.

## Prepare the route

Open the Submission mode and the checkpoint, and in the “Signing” card click “Send for signing”. The “Send for signing” screen opens. Changes are saved automatically, there is no separate save button.

### Checkpoint documents

Every document has to be built: a document that is not built has a “Build” button. A document that is already being signed on another route is marked “out for signing in another route”.

### Who signs and in what order

- Steps go in order, people in one step sign in parallel. The template sets the default order: usually the authors, then the supervisor and the co-supervisor in one step, then the academic supervisor.
- Drag people and steps to reorder them. A person's menu has “Same step as previous”, “Separate step” and “Remove”.
- Each person shows whether they are a member, “invitation sent” or “not in project”, the signing method (“Image”, “E-signature”, “E-signature in PDF”), whether their signature is ready and how many actions they will have (below).
- “Add approver” adds a person who only approves the document, without a signature on the page.
- The “freeze after this step” mark shows after which step the final PDF is frozen.

### Where the signatures go

Document tabs and a PDF page with signature frames, just like on a document's “Signatures” tab: you can drag a frame.

- A signature marked “not placed” goes on the open page with “To page N”. A signature on another page can be shown with “Go” or moved to the open page with “Here”.
- A signature the checkpoint does not require (for example, the academic supervisor on an application) is added with “Add signature: …” and removed with the cross “Remove signature from route”.

### Your signature

If you sign the checkpoint's documents yourself, get your signature ready before sending:

- with an image: “Upload or draw”;
- with an electronic signature: the Studio needs the plate details, that is a key or a certificate. The line “Key: …” means everything is ready. If you have no key, create one in the signing settings or sign later on your page.

If you are in the first step, sending counts as your approval.

### Deadline and message

Both fields are optional. Signers see the deadline on the signing page, in the Inbox and in the email; a missed deadline is marked red, but the route is not cancelled. The message to signers shows on the signing page, for example “Please sign by Friday”.

### What blocks sending, and sending

The bottom of the screen lists “What blocks sending”. While the list is not empty, you cannot send.

| Blocker | What to do |
|---|---|
| the document is not built | click “Build” in “Checkpoint documents” |
| already out for signing in another route | wait for it to finish or cancel that route |
| not in the project, invite them | click “Invite” next to the person |
| no one to sign | no person has the slot's persona: invite or pick someone |
| the signature is not placed on the page | click “Go to placement” and place the frame |
| your signature is not ready | upload an image or set a key in “Your signature” |

When you see “Ready to send.”, click “Send for signing”.

If the documents are frozen right when you send and you sign with a Studio key, there is also a “Send and sign” button: it sends the route and adds your electronic signature at once (asking for the key passphrase if it has one). If the signature fails at that point, the route is still sent: the Studio says “The route is sent, but your signature is not in place” and offers to sign on your page.

## How many actions each person has

Next to each person the Studio says what they will have to do:

| Hint | What it means |
|---|---|
| sending is the approval | you are in the first step: sending counts as your approval |
| 1 action | one click on the signing page |
| 2 actions: approve, then sign the final PDF | they approve first, and a second request comes once the final PDF is frozen |
| will choose the method when signing | the checkpoint allows several methods, the person picks one |
| will upload a signature when signing, will set a key when signing | the person adds the image or the key on their page |

Under the sending form the Studio says when the final PDF is frozen: “The documents are frozen right when you send” or “The documents are frozen after step N, then e-signatures go on the final PDF”.

!!! tip "Fewer actions"
    Image signatures before e-signatures mean fewer actions. If the people who sign with an electronic signature come after everyone who signs with an image, each of them approves and signs with one click.

## Follow the progress

The “Signing” card on the checkpoint page shows the step and whose turn it is, for example “Step 2 of 3. Waiting for Petrov P. P. (supervisor)”, since when they have been waiting, how many signatures are in place and the deadline. Each person shows their state: “waiting”, “to approve”, “approved”, “to sign the final PDF”, “signed”, “has not accepted the invitation”, “returned for rework”.

The person whose turn it is has two buttons:

- **“Remind”** sends a reminder to the Inbox and by email, if email is configured. At most once every 12 hours per person; the hint on the button says when you can remind again. For someone who has not accepted the invitation yet, “Remind” sends the invitation again.
- **“Copy link”** is for sending the link yourself, for example in a messenger. For a member it is the link to their signing page, which opens after signing in. For an invitee on a server without email it is a new invitation link: every click makes a new one and the previous one stops working, so send the latest. If the server has email, invitees have no such button: the invitation goes by email, and “Remind” sends it again.

The server also reminds the person whose turn it is on its own: a day before the deadline and after three days of waiting, at most three times per sending.

Other buttons on the card:

- **“Open route”** shows the route. While it is running it cannot be changed.
- **“Cancel route”**, after a confirmation, stops the signing. Everyone who already got a request is notified, electronic signatures already made stay. You can fix the route and click “Send again”.
- **“Go to signing”** shows when it is your turn. If you sign with an electronic signature, the card reminds you: “The route is sent, your signature is not in place yet”.

While the route is running, the editor of its documents shows the banner “This document is out for signing (step k of n). Editing and rebuilding will stop the route”. The signatures of these documents cannot be changed on the “Signatures” tab.

## What stops the route

The route makes sure the supervisors sign exactly the version they saw. If a document changes, the route stops, and you and those who already approved get a notification.

| What happened | What the card says |
|---|---|
| the document was rebuilt with changes: a text edit, a template update, a restore from history, a sync | “The document changed after approval: the route is stopped.” |
| signatures on the pages were changed outside the route | “Signatures on the pages changed: the route is stopped.” |
| the final PDF changed outside the route, for example through git | “The frozen PDF changed: the route is stopped.” |
| a signer left the project or their role or persona changed | “A participant left the project: assign someone else and send again.” |

- Rebuilding a LaTeX document without edits does not stop the route: the PDF comes out the same. A document built from Word or PowerPoint comes out different on every rebuild, so rebuilding it stops the route.
- Comments, other documents and their builds do not affect the route.
- If one electronic signature is deleted or becomes invalid, the route does not stop: it waits for that slot again.

### Send again

Fix the document, build it and click “Send again” on the card. The people and steps stay the same. If something blocks sending, the Studio opens the route screen, where you can see it.

The route starts again from the first step, but people whose documents did not change do not have to approve again. A signer's image and key are kept, so approving again is one click for them.

## Returned for rework

Instead of signing, a signer can return the documents with a comment. You get a notification and an email, and the card shows, for example, “Petrov P. P. returned it for rework: “Clarify the project goal””. Under it are “Open document” and “Send again”. Detailed remarks on the text are left as comments in the project itself.

## Everyone has signed

The card says “Everyone has signed. You can build the package.”, and you get a notification and an email. Build the package with “Package” on the same checkpoint page: it gets the signed PDFs and the electronic signature files ([Submission and packaging](submit.md)).

A completed route keeps watching the documents. If you edit and rebuild a document, the route stops and asks you to send again. If someone's signature disappears, the route waits for that one again. To make the route stop watching, click “Stop tracking”. A new route for the same checkpoint starts with “New route” on the route screen.

## Questions and answers { #faq }

**The server has no email.**
Requests and reminders still arrive in the Inbox, on the “To sign” tab; there are no emails. Send the person the link yourself with “Copy link” on the card. If they have not accepted the invitation yet, the button makes a new invitation link and the previous one stops working. Automatic reminders do not go to an invitee without an account.

**The supervisor has no account.**
Invite them by email from the route with “Invite”. Using the invitation link they sign up with that same address, click “Accept” and land on the signing page. If registration on the server is closed, first ask the administrator to create an account for them.

**The order is wrong.**
While the route is not sent, drag the steps. If it is already sent, click “Cancel route”, fix the order on the route screen and click “Send again”. Approvals of people whose documents did not change are kept.

**A signer left the project.**
The route stops with “A participant left the project: assign someone else and send again”. Open the route, pick or invite another person with the same persona and click “Send again”. A route that is already completed does not care: the signatures are in place.

**The “out for signing” banner.**
The document was sent for signing and the route is running. You can still edit the text and build, but a rebuild with changes stops the route and you will have to send it again. The signatures of this document cannot be changed on the “Signatures” tab: cancel the route on the checkpoint page first.

**“Sign the submission” says “The document is on a signing route”.**
Route documents are signed only in turn, on the signing page. Click “Open the signing page” in the submission dialog.

## For the administrator

Route emails go out only when email is configured ([Server emails](../deploy/mail.md)). What a signer can do with an electronic signature depends on whether keys may be stored on the server (admin, “Signing keys”): without that, CryptoPro and a ready signature file remain.

| Variable | Default | Meaning |
|---|---|---|
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_INTERVAL_S` | `900` | how often the server checks whom to remind, in seconds |
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_BEFORE_DEADLINE_HOURS` | `24` | how many hours before the deadline the reminder goes out |
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_WAITING_DAYS` | `3` | after how many days of waiting the reminder goes out |
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_MAX_AUTO` | `3` | how many automatic reminders a person gets per sending; `0` turns them off |
| `HSE_STUDIO__SIGNING_ROUTE__SWEEP_INTERVAL_S` | `300` | how often the server checks running routes against the documents, in seconds |

The manual “Remind” is limited to once every 12 hours per person, and this is not configurable. All settings: [Environment variables](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md).
