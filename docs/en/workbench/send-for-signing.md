---
title: Send for signing
description: How to send a checkpoint's documents to supervisors for signing in order on a shared server, follow the progress, edit documents while they are being signed, send a new version and build the package.
tags:
  - Workbench
  - Submission
  - Signatures
---

# Send for signing

<p class="hds-lede">On a shared server you can send a checkpoint's documents to your supervisors for signing. The Studio keeps the order itself: each person gets a request in their turn and signs on their own page, and you see who has the documents now.</p>

## When to use it { #when }

When other people have to sign the checkpoint's documents: the supervisor, a co-supervisor, the academic supervisor. You do not have to explain to everyone where their signature goes or make sure the academic supervisor does not sign before the supervisor.

- It works only on a Studio server. A local Studio has no such button: sign your own slots with “Sign the submission” or send the supervisor the [files for signing](submit.md#detached-signatures).
- The project owner and editors can send. In a team project there is one route for the whole team, and the authors sign in parallel.
- Only a person signed in to their own account can sign: the link in the email opens the signing page after signing in.

## How signing goes { #how-it-goes }

1. You prepare the route: who signs, in what order and where the signatures go.
2. You click “Send for signing”. The Studio keeps the built PDF of each document: this is the version for signing. Signers see and sign exactly that version.
3. The first person in line gets a request in the Inbox and by email, if the server sends email. They open the signing page, look at the PDF and approve or sign.
4. The next step gets its request once the previous one is done. People in one step sign in parallel.
5. When all visible signatures are in place, the Studio freezes the final PDF, and those who sign with an electronic signature add it.
6. Everyone has signed: build the package. It gets the signed version.

While the documents are out for signing you can still edit and build them: the route goes on, and your edits do not reach the version being signed. To have the corrected text signed, send a new version ([below](#new-version)).

What a signer sees is described in [How to sign](how-to-sign.md).

!!! note "Why electronic signatures come last"
    An electronic signature covers the exact bytes of the PDF. Signature images and the plates of electronic signatures are printed in that same PDF. If another image is added to a page after an electronic signature, the file changes and the signature already made becomes invalid. So first everyone approves the document in turn, and the visible signatures appear as they do. Then the Studio freezes the final PDF once, and electronic signatures go on that file. This way no signature breaks another.

## Invite the signers { #invite }

A signer is a project member with the “Reviewer” role and a persona: “Supervisor”, “Co-supervisor” or “Academic supervisor”. The persona tells the Studio which signature slots are theirs.

- If the person is not in the project yet, the route shows “not in project” next to them and an “Invite” button. It opens the usual invitation form with the “Reviewer” role and the right persona already chosen: enter the email and click “Invite”. After accepting the invitation from the link, the person lands right on the signing page. Someone who already has an account gets the invitation in the Inbox: if it is already their turn after “Accept”, the Studio opens the signing page right away, otherwise the documents appear on the “To sign” tab when their turn comes.
- You can also invite people in advance in the project settings, “People” section. More: [Invitations and access requests](../deploy/invitations.md).
- If several people have the persona, pick one in the “Who signs” list.
- You can send while an invitation is still pending: that person's step will wait.
- Inviting from the route needs the right to share the project: the owner or an editor with “Can share”. If registration on the server is closed, you can only invite people who already have an account.

## Prepare the route { #prepare }

Open the Submission mode and the checkpoint, and in the “Signing” card click “Send for signing”. The “Send for signing” screen opens. Changes are saved automatically, there is no separate save button.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval/route</span></div>
    <img src="../assets/shots/signing-route.en.light.webp#only-light" alt="Route screen">
    <img src="../assets/shots/signing-route.en.dark.webp#only-dark" alt="Route screen">
  </div>
  <figcaption>the “Send for signing” screen: checkpoint documents, steps in order and the “What blocks sending” list</figcaption>
</figure>

### Checkpoint documents

Every document has to be built: a document that is not built has a “Build” button. A document held by the route of another checkpoint is marked with that checkpoint's name: “out for signing on the route “…”” or “held by the completed route “…””.

A document replaced with your own file (“Replace with my own file…” on the document screen) counts as built, and the uploaded PDF is what gets signed: it becomes the version for signing, the boxes and date marks sit on it. Signatures already inside the uploaded PDF (a scan with a signature, or a PDF signed in another program) the Studio does not see and does not check. If the route needs that signature, upload it as an image into the slot or sign on the signing page.

### Who signs and in what order

- Steps go in order, people in one step sign in parallel. The template sets the default order: usually the authors, then the supervisor and the co-supervisor in one step, then the academic supervisor. When the template sets the checkpoint's whole route, the top of the screen shows “From the template” ([Route from the template](#preset)).
- Drag people and steps to reorder them. A person's menu has “Same step as previous”, “Separate step” and “Remove”.
- Each person shows whether they are a member, “invitation sent” or “not in project”, the signing method (“Image”, “E-signature”, “E-signature in PDF”), whether their signature is ready and how many actions they will have (below).
- “Add approver” adds a person who only approves the document, without a signature on the page.
- The “freeze after this step” mark shows after which step the final PDF is frozen.

### Where the signatures go

Document tabs and a PDF page with signature frames, just like on a document's “Signatures” tab: you can drag a frame.

- A signature marked “not placed” goes on the open page with “To page N”. A signature on another page can be shown with “Go” or moved to the open page with “Here”.
- A signature the checkpoint does not require (for example, the academic supervisor on an application) is added with “Add signature: …” and removed with the cross “Remove signature from route”.
- “Add date” on a signature adds a date mark: the day the person approves is printed in the right spot of the page ([Signing date](#dates)).
- A signer may change the method on their step, but an image and an electronic signature with a plate are offered only if their signature is placed on the page. Without a place they are left with “E-signature in PDF” without a mark. If they switch from an image to an e-signature and the place is narrow, the Studio widens it to 70 mm leftwards from its right edge so the e-signature plate fits.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval/route</span></div>
    <img src="../assets/shots/signing-placement.en.light.webp#only-light" alt="Where the signatures go">
    <img src="../assets/shots/signing-placement.en.dark.webp#only-dark" alt="Where the signatures go">
  </div>
  <figcaption>“Where the signatures go”: frames on the PDF page, the supervisor signature is placed, “Ready to send.”</figcaption>
</figure>

### Your signature

If you sign the checkpoint's documents yourself, get your signature ready before sending:

- with an image: “Upload or draw”;
- with an electronic signature: the Studio needs the plate details, that is a key or a certificate. The line “Key: …” means everything is ready. If you have no key, create one in the signing settings or sign later on your page.

If you are in the first step, sending counts as your approval.

### Deadline and message

Both fields are optional. Signers see the deadline on the signing page, in the Inbox and in the email; a missed deadline is marked red, but the route is not cancelled. The message to signers shows on the signing page, for example “Please sign by Friday”.

The route deadline comes from the checkpoint deadline ([Submission deadline](submit.md#deadline)). If the checkpoint has a deadline, the Studio sets the route deadline itself when it creates the draft: one day before the checkpoint deadline, at the same time. After the last signature you have a day to build the package and upload it to the LMS. If less than two days are left before the checkpoint deadline, the route deadline equals it; if the checkpoint deadline has already passed, the route deadline is empty. Under the “Deadline” field the Studio shows where it comes from:

- “Route deadline: 14.11, 23:59. One day before the checkpoint deadline (15.11), so there is time to build the package”.
- If the checkpoint deadline changed after the draft was created: “The checkpoint deadline changed: 20.11, 23:59. Set the route deadline to 19.11, 23:59?” and a “Set” button. The route deadline itself does not change until you press “Set”.
- If the route deadline is empty (the checkpoint deadline was set after the draft was created), the Studio suggests it with the same button: “Checkpoint deadline: 15.11, 23:59. Set the route deadline to 14.11, 23:59?”.
- You can set any other route deadline in the “Deadline” field. If it is later than the checkpoint deadline, the Studio warns: “The route deadline is later than the submission deadline”.
- If the checkpoint has no deadline, this is the same “No submission deadline” line as on the checkpoint page, with the field and a “Set deadline” button.

The deadline of a route already sent does not change by itself when the checkpoint deadline changes: the signers already got it in the request.

### What blocks sending, and sending

The bottom of the screen lists “What blocks sending”. While the list is not empty, you cannot send.

| Blocker | What to do |
|---|---|
| the document is not built | click “Build” in “Checkpoint documents” |
| out for signing on the route of the checkpoint “…” | a document is signed on one route at a time: “Open that checkpoint” takes you to its page, cancel that route there |
| held by the completed route of the checkpoint “…” | a completed route watches its documents until it stops being tracked: open that checkpoint with “Open that checkpoint” and click “Stop tracking” |
| not in the project, invite them | click “Invite” next to the person |
| no one to sign | no person has the slot's persona: invite or pick someone |
| the signature is not placed on the page | click “Go to placement” and place the frame |
| your signature is not ready | upload an image or set a key in “Your signature” |

When you see “Ready to send.”, click “Send for signing”.

If the documents are frozen right when you send and you sign with a Studio key, there is also a “Send and sign” button: it sends the route and adds your electronic signature at once (asking for the key passphrase if it has one). If the signature fails at that point, the route is still sent: the Studio says “The route is sent, but your signature is not in place” and offers to sign on your page.

## Route from the template { #preset }

A template can set a checkpoint's whole route: the order of signers, signatures beyond the checkpoint items and when they are needed, optional signatures, and signature places and date marks on the pages. Then the route is ready the first time you open “Send for signing”: check it, invite the people who are not in the project yet, prepare your own signature and send. The template does not set people: they come from the project.

!!! note "Which templates can do this"
    A route from the template appears only in projects on a template version that defines one. For the MSc SSE course project (`hse-cs-sse`) the route and the signature places on the template's signature lines come with template version 2026.1.5 ([below](#preset-sse)): a project on 2026.1.4 or an earlier version gets them by updating from the overview card ([Updating to 2026.1.5](submit.md#sse-2026-1-5)). While the template version defines no route, the screen works as before: the default order, and you place the signatures yourself; there is no “From the template” or “Changed by you”.

    The place marks (“Place from the template”, “Place changed”) show on such versions too. There the template knows only one common place per signature for all documents, usually not on the right line. So “Place changed” on a box you moved onto the signature line is fine: you do not need to reset it.

**What the template does when you first prepare the checkpoint's route.**

- The steps follow the template's order.
- Signatures beyond the checkpoint are added on a condition about the project's people: for example, the academic supervisor's consent on the application only if the supervisor is not from HSE, or the consultant's signature only if the project has a consultant. “Not from HSE” comes from the “HSE / Not HSE” switch of the supervisor in the project settings.
- Signatures the template treats as optional at this checkpoint are already marked “Signature optional” ([Optional signatures and skipping](#optional)).
- Signature places and date marks go onto the pages and are switched on. Places you already set or moved yourself are left alone. So are documents held by another checkpoint's route and documents whose final PDF already carries e-signatures.

If the checkpoint already had a route (cancelled or completed), the new route takes the people and the order from it, and the template only adds places that are missing.

**Marks in the route editor.**

| Where | Mark | What it means |
|---|---|---|
| top of the screen | “From the template” | the order, the extra signatures and the “optional” marks are as in the template |
| top of the screen | “Changed by you”, “differs: order, extra signatures, “optional” marks” | you changed something; next to it is “Reset to template” |
| top of the screen | “The new template version has a different route for this checkpoint” | the route was built from the previous template version, and after the update the template sets a different one; the same “Reset to template” button |
| “Where the signatures go”, on a signature beyond the checkpoint | “added by the template: the supervisor is not from HSE” or “added by you” | who added the signature and why |
| “Add signature: …” | “The template adds this signature only if the supervisor is not from HSE” | the template did not add it because the condition is not met; you can still add it yourself |
| next to the “Signature optional” checkbox | “as in the template” | the template set the mark |
| next to a signature box | “Place from the template” | the place and the date marks are as in the template |
| next to a signature box | “Place changed” and “Reset place to template” | you moved the box or changed the date marks |
| next to a signature box | “Placed on the template line” | the place is as in the template and sits on a line of the built document; after a build it follows the line ([Signature places on the template lines](#anchors)) |
| under the signature | “The built document has no line for this signature…”, “The template place appears after the document is built”, “The uploaded PDF has no template lines…” | there is no place on a line; what to do is in [Signature places on the template lines](#anchors) |

The place marks are on the document's “Signatures” tab too.

**You can change everything**, just as without a template: steps and people, “Add signature: …” and “Remove signature from route”, the “Signature optional” checkbox, places and date marks. The only thing you cannot do is mark optional a signature the template requires.

**Reset to template.** The button at the top of the screen shows when the route is not sent yet, or is stopped, returned or cancelled, and differs from the template. The Studio asks “Reset to the template?”: “The order, the extra signatures and the “optional” marks will be as in the template. People stay if their role is in the template. Signature places on the pages will not change”. Buttons “Reset” and “Cancel”. A person whose role is in the template stays on their new step together with their approval; missing people are picked from the project.

**Reset place to template.** The button next to a box marked “Place changed”: the place and the date marks of this signature on this document become as in the template; whether the signature is switched on does not change. Other places and the route composition are left alone. If the document's final PDF already carries e-signatures, the Studio first asks “Reset the place to the template?” and names whose signatures will be reset, as with date marks ([Signing date](#dates)). On a document under a running or completed route, the place is reset by whoever manages the route, and the route history shows “changed the date marks”.

Two buttons rather than one, because a place is your work on a specific page while the route composition is a decision about the checkpoint: resetting one and losing the other would be a surprise.

**What the template never touches by itself.** Routes already sent: running, stopped, completed (a stopped one can be reset to the template only with the button). And places you set or moved yourself: a manual place stays manual after a template update too.

**Template update.** New routes take the new version's route right after the update. Places marked “Place from the template”, and places the Studio set itself and you never touched, move to the new version's places. The update preview in the project settings (“Template version”) says how many places will move and how many will not: “Template signature places will be updated: 3”, “Not updated: changed by you 1, on a signing route 2, signed 1”. If no template files change but places do, it says “No files change. Template signature places will be updated: 3”.

If the new version's places sit on the template lines and the lines of the current build are unknown, the preview says “Signature places will follow the template lines after the build: 2”: the places move to the new version right away and land on the lines at the next build.

- Places changed by you, places on documents under a route and on documents whose final PDF carries e-signatures are not updated.
- The update does not change route compositions or “optional” marks. If a draft's route differs in the new version, the editor shows “The new template version has a different route for this checkpoint”.
- Undoing the update in the project settings brings the places back too, if you did not touch them after the update.

Over MCP the route from the template is read-only ([MCP](mcp.md)). Sending over MCP (`send_for_signing`) applies the template just like the button.

### MSc SSE course project 2026.1.5 { #preset-sse }

At the “Topic application (SmartLMS)” checkpoint the route is set up by itself as soon as you open “Send for signing”:

1. the author;
2. the supervisor and the consultant in one step; the consultant only if the project has one (the full name is filled in);
3. the academic supervisor, only if the supervisor is not from HSE (the “HSE / Not HSE” switch of the supervisor in the project settings).

The template adds the consultant's and the academic supervisor's signatures on the same conditions on which the topic application prints their lines, and does not mark them optional: these are signatures the form asks for. The boxes already sit on the document's lines: on the “Signature” lines of the application and in item 6 of the project description above the date line. The supervisor's date marks sit on the date line of the project description: day and month in words on the Russian page, day and month as numbers on the English one; the template prints the year. At the “Course project defence” checkpoint the author's box and date sit on the “Signature, date” line of the report title page. How the boxes stick to the lines is described below: [Signature places on the template lines](#anchors).

The template does not set people: you still need to invite the supervisor, the consultant and the academic supervisor if they are not in the project yet.

## Signature places on the template lines { #anchors }

A document's layout depends on the project data: the English application is shorter than the Russian one, the consultant line is printed only when the project has one, and a long title or the supervisor's long position pushes the date line of the project description down. A place in millimetres would fit only one layout. So a template can tie a place to a line of the document itself: during the build it records where the “Signature” line or the date line is, and the Studio puts the box on it. These records print nothing on the PDF. The MSc SSE course project works this way from version 2026.1.5.

**Marks next to a signature** in “Where the signatures go” and on the document's “Signatures” tab:

| Mark | What it means | What to do |
|---|---|---|
| “Placed on the template line” | the box sits on a line of the built document and follows the line by itself after the next build | nothing |
| “Place from the template” | a template place in millimetres: the Studio does not know the lines of this build (below), and the box sits on the template's fallback place | build the document; if the box is still off the line, move it |
| “The built document has no line for this signature. Check the project data or place it manually” | the document has no line for this signature: for example, the academic supervisor is on the route while the supervisor is “HSE” in the project settings, so the application prints no consent line. There is no place, and the earlier template place is switched off so the image does not land on someone else's line | fix the project data and build the document, or place it manually |
| “The template place appears after the document is built” | the lines are not known yet, and the template has no fallback place for this signature | build the document |
| “The uploaded PDF has no template lines: place it manually” | the document is replaced with your own PDF | place the box yourself |

**After a build.** Places the Studio set and you never touched land on the lines of each new build. If some places moved, the Studio says “Template signature places moved to the new layout: N”, and the same mark stays on the “Build” tab. A build without edits does not move places. If a line comes back (for example, you set the consultant again), the box lands on it switched off: switch it on yourself or click “Reset to template”.

**What never moves.**

- A manual place: a box you set or moved yourself (“Place changed”). To put it back on the line, click “Reset place to template”.
- A document under a route. The signers sign the version out for signing, and new builds do not change its place. The places follow the lines of the new build only when you click “Send new version”: the document is signed again then anyway ([Send a new version](#new-version)).
- A document whose final PDF already carries e-signatures: the place stays where it was signed.
- Your own uploaded PDF: it has no template lines, you place the box. The template's fallback place does not apply to it either.

**When the lines are unknown.** The Studio knows the lines only of the build that recorded them. They are unknown if the document has not been built yet, if a runner older than 0.27.0 built it, or if the PDF was uploaded to the server from the local Studio. Then a new box goes to the template's fallback place in millimetres (for the course project 2026.1.5 these are the places of the Russian application without the consultant line) marked “Place from the template”, and a place already set is left alone. Date marks have no fallback place: they appear after a build whose lines are known. If signature places do not land on the lines after a build on the server, ask the administrator to update the runners ([Runners](../deploy/runners.md#runner-version)). In the local Studio its own build records the lines; the places it computes reach the server through git sync.

## How many actions each person has { #actions }

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

A date mark on an e-signature counts as a visible signature: such a signer approves before the final PDF is frozen, and if someone after them still adds a visible signature, they have 2 actions ([Signing date](#dates)).

## Follow the progress { #progress }

The “Signing” card on the checkpoint page shows the step and whose turn it is, for example “Step 2 of 3. Waiting for Petrov P. P. (supervisor)”, since when they have been waiting, how many signatures are in place and the deadline. Each person shows their state: “waiting”, “to approve”, “approved”, “to sign the final PDF”, “signed”, “has not accepted the invitation”, “returned for revision”.

Below the people is the list of route documents. Each has the line “Version for signing from …”: when the version being signed was taken. The “Open the version for signing” link shows exactly that version, not the current build.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval</span></div>
    <img src="../assets/shots/signing-card.en.light.webp#only-light" alt="The “Signing” card">
    <img src="../assets/shots/signing-card.en.dark.webp#only-dark" alt="The “Signing” card">
  </div>
  <figcaption>the “Signing” card: the step, whose turn it is, each person’s state and the version for signing</figcaption>
</figure>

People on the route have two buttons:

- **“Remind”** is there for the person whose turn it is and for anyone who has not accepted the invitation yet. It sends a reminder to the Inbox and by email, if email is configured. At most once every 12 hours per person; the hint on the button says when you can remind again. For someone who has not accepted the invitation yet, “Remind” sends the invitation again.
- **“Copy link”** is there for everyone who has not signed yet, even before their turn: you can send the links in advance. It is for sending the link yourself, for example in a messenger. For a member it is the link to their signing page, which opens after signing in. Until their turn comes, the page says “Not your turn yet”, and when it comes, they get a notification. For an invitee on a server without email it is a new invitation link: every click makes a new one and the previous one stops working, so send the latest. If the invitee already has an account, it is a link to the Inbox, where the invitation is waiting. If the server has email, invitees have no such button: the invitation goes by email, and “Remind” sends it again.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval</span></div>
    <img src="../assets/shots/signing-link.en.light.webp#only-light" alt="Copy link">
    <img src="../assets/shots/signing-link.en.dark.webp#only-dark" alt="Copy link">
  </div>
  <figcaption>“Copy link”: the signing page address is in the clipboard</figcaption>
</figure>

The server also reminds the person whose turn it is on its own: a day before the deadline and after three days of waiting, at most three times per sending.

Other buttons on the card:

- **“Open route”** shows the route. While it is running it cannot be changed.
- **“Cancel route”**, after a confirmation, stops the signing. Everyone who already got a request is notified, electronic signatures already made stay. Signature images of people who have not approved yet stay hidden: cancelling is not their approval. The version for signing is removed, and the documents are signed from the current build again. You can fix the route and click “Send again”.
- **“Go to signing”** shows when it is your turn. If you sign with an electronic signature, the card reminds you: “The route is sent, your signature is not in place yet”.

While the route is running, the editor of its documents shows the banner “This document is out for signing (step k of n). Signers sign the version from …; your edits do not go into it.” The signatures of these documents cannot be changed on the “Signatures” tab.

## Editing while signing { #editing }

The route signs the version taken when it was sent. The working build lives separately, so you can edit and build a document while it is being signed: the route goes on, the signers notice nothing and get no notifications about your edits.

Before the first edit of a document out for signing the Studio asks: “Document out for signing. Changes will not reach the version being signed. Continue?” The buttons are “Continue” and “Cancel”. “Cancel” leaves everything as it was.

- The question comes on the first text edit in the editor, on “Build”, when opening the office editor, when uploading or replacing the document's file and when changing files in the tree.
- Shared files (`common/`, the bibliography) and project fields (metadata, authors, supervisors, language) affect several documents at once. Then there is one question with a list: “Out for signing: …”.
- A template update plan shows a similar line if the update touches documents out for signing: “Out for signing: … The update will not reach the version being signed: afterwards the route asks you to send a new version (“Send new version” on the Signing card)”. The route does not stop; the document shows “There are changes”. The signers still see the earlier version; to have them sign the updated form, send a new version. The update does not change the composition of a running route: for example, if the new version of the application has no academic supervisor consent line but the academic supervisor is on the route, mark their signature optional and skip them when their turn comes ([Optional signatures and skipping](#optional)), or cancel the route and remove them.
- The question is asked once per session per document. After a new sending it is asked again.
- Only a running route asks. If the route is stopped, returned or completed, edits are expected and there is no question.
- Edits from a local Studio, git sync and MCP go through without the question. They do not touch the version being signed either.

When the built PDF differs from the version for signing, the “Signing” card says “There are changes since it was sent for signing. Signers sign the version from …”, and the document is marked “changed since sending”. Signers still sign the version that was sent. To have them sign the corrected text, send a new version.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval</span></div>
    <img src="../assets/shots/signing-version-card.en.light.webp#only-light" alt="Changes since sending">
    <img src="../assets/shots/signing-version-card.en.dark.webp#only-dark" alt="Changes since sending">
  </div>
  <figcaption>the application was rebuilt after sending: the route goes on, the card offers “Send new version”</figcaption>
</figure>

- Unbuilt edits do not count: the changes show up after a build.
- A LaTeX document rebuilt without edits gives the same PDF, so there is no mark (on the server, when a runner 0.27.0 or newer built it, [below](#faq)). A document from Word or PowerPoint comes out different on every rebuild, so after any rebuild the card shows changes. You do not have to send a new version in that case.

## Send a new version { #new-version }

The “Send new version” button appears on the card when at least one route document has changed since sending. It works for a running, stopped, returned and completed route.

Before sending, the Studio shows what will happen:

- “Changed: …”: for these documents the current build becomes the new version for signing;
- “Approve again: …”: people who already approved the changed documents;
- “Unchanged: …, its signatures stay”: documents that did not change.

The “What changed” field is optional. The text goes to the signers together with the request, for example “The topic wording is fixed”: on the signing page it is the author's message, and in the email it is under “Message from the sender”. The buttons are “Send new version” and “Don't send”.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval</span></div>
    <img src="../assets/shots/signing-new-version.en.light.webp#only-light" alt="Send a new version">
    <img src="../assets/shots/signing-new-version.en.dark.webp#only-dark" alt="Send a new version">
  </div>
  <figcaption>the “Send a new version?” confirmation: what changed and a note for the signers</figcaption>
</figure>

What happens after sending:

- **Unchanged documents** keep their version for signing, approvals, signature images and electronic signatures. People who sign only those do nothing and get no notification.
- **Changed documents** are approved again in order, from the first step. Whoever already approved or signed such a document but whose turn has not come yet gets “A new version is out for signing: …” in the Inbox; the request comes in their turn. The person whose turn it is gets “… asks you to sign a new version: …”.
- **Electronic signatures** on a changed document are made again: the final PDF is frozen from the new version once all visible signatures are on it.
- The people and the order stay the same. To change them, cancel the route first.

If no document changed, there is nothing to send: there is no button, and a stopped, returned or cancelled route shows “Send again” instead.

## What stops the route { #stops }

Text edits, builds, template updates, restoring sources from history and sync do not stop the route: the document just shows changes. The route is stopped by people and by signature changes made outside the route. Then you and those who already approved get a notification.

| What happened | What the card says |
|---|---|
| a signer returned the documents for revision | “… returned it for revision: “…”” |
| you cancelled the route | “The route is cancelled.” |
| a signer left the project or their role or persona changed | “A participant left the project: assign someone else and send again.” |
| the version for signing changed outside the route, for example through git or by restoring the service folder | “The version out for signing changed outside the route: the route is stopped.” |
| signatures on the pages were changed outside the route | “Signatures on the pages changed: the route is stopped.” |
| the final PDF changed outside the route, for example through git | “The frozen PDF changed: the route is stopped.” |

- The last three stops cannot be caused through the server interface: during the route only the route itself changes the version for signing, the final PDF and the signatures on the pages.
- Comments and documents outside the route do not affect it.
- If one electronic signature is deleted or becomes invalid, the route does not stop: it waits for that slot again.

### Send again { #resend }

Remove the reason for the stop and click the button on the card. If the documents changed, it is “Send new version” ([above](#new-version)). If not, for example you replaced a participant who left, it is “Send again”: the version for signing stays the same. If something blocks sending, the Studio opens the route screen, where you can see it.

The route starts again from the first step, but approvals of documents that did not change are kept. A signer's image and key are kept, so approving again is one click for them.

## Returned for revision { #returned }

Instead of signing, a signer can return the documents with a comment. The route stops, you get a notification (and an email, if email is configured), and the card shows, for example, “Petrov P. P. returned it for revision: “Clarify the project goal””. Under it is “Open document”. Fix the document, build it and click “Send new version”: only the changed documents are approved again. Detailed remarks on the text are left as comments in the project itself.

## Everyone has signed { #completed }

The card says “Everyone has signed. You can build the package.”, and you get a notification (and an email, if email is configured). Build the package with “Pack” on the same checkpoint page: it gets the signed PDFs and the electronic signature files ([Submission and packaging](submit.md)).

A completed route keeps watching the signatures. Edits and rebuilds do not stop it: the signed version stays, and the card says “Everyone signed the version from …. There are changes since it was signed.” and offers “Send new version”. If someone's signature disappears, the route waits for that one again. To make the route stop watching, click “Stop tracking”. A new route for the same checkpoint starts with “New route” on the route screen.

### The package from the signed version { #pack }

The package and the “With signatures” PDF are built from the version for signing, even if the working build is newer. This way the package gets exactly what was signed.

If a document changed after sending, the package card warns before the build: ““…” changed after it was sent for signing: the package will get the version for signing of …”. After the build the same line stands under “Package built with warnings”. This is not an error: the package is built. If the package needs the corrected text, click “Send a new version” next to it: the button leads to the “Signing” card of this document's route. The owner and editors see it while the route is running or completed.

In the `КАК_ПРОВЕРИТЬ.txt` guide such a document has the line “Версия от …, SHA-256 исходного PDF …” (version date and the SHA-256 of the source PDF): it tells the reviewer which version was signed.

### The document's “Signatures” tab { #signatures-tab }

The top of the “Signatures” tab shows which version is signed: “Being signed: the version of …” for a running route, “Signed: the version of …” for a completed one, “Version for signing of …” after “Stop tracking”. Below are the start of the SHA-256, the “There are changes since the document was sent for signing” note when it applies, and the “Open the version for signing” button.

The version for signing stays after the route is completed and after “Stop tracking”: the signatures belong to it, however much you edit the text. If you no longer need the signatures on it and the document has to be signed from the current build, click “Sign the current build” and confirm. Signatures placed on the old version will no longer match the document.

- The button is available to whoever can edit the document's files.
- While a route holds the document (running, stopped, returned, or completed and still tracked), the button is disabled. First send a new version, cancel the route or stop tracking it.
- Cancelling the route removes the version for signing by itself.

## Optional signatures and skipping { #optional }

Sometimes a signature is not needed at this checkpoint: for example, the supervisor has already approved the application, and the academic supervisor's signature was added by the author or turned out to be redundant. The route waits for that person and will not complete until they sign. To avoid cancelling the route, mark the signature optional, and when the person's turn comes, skip them.

**Mark a signature optional.** On the document's "Signatures" tab, in the slot panel, tick "Signature optional at this checkpoint". The same checkbox is in the route editor, in the "Where the signatures go" block, next to every signature place (there it is called "Signature optional"). The mark belongs to the checkpoint: the same document at another checkpoint may still require the same signature. You can change the mark on a running route, it does not touch the document's visible layer. You cannot mark a signature the template requires ("The template requires this signature: it cannot be made optional") or one that is already in place.

**Skip.** In the "Signing" card, next to the person whose turn it is, you see the hint "All of this person's signatures at this checkpoint are optional. They can be skipped" and the "Skip" button. Only the people who manage the route (the owner and editors) see it, and only when all of the person's remaining signatures at the checkpoint are optional. While at least one is required, skipping is refused: "There are required signatures: cannot skip". You cannot skip before the person's turn: "You can skip once it is their turn". If the person has already signed some places, those stay, only the remaining ones are skipped.

Studio asks you to confirm: "Skip ...?" The window lists the signatures that will not be placed and what happens next: the route moves to the next step, freezes the documents and asks the e-signature signers, keeps waiting for others, or completes ("All signatures will be collected"). The buttons are "Skip" and "Do not skip".

**What happens after a skip.**

- The skipped person gets an inbox notification and an email, if mail is set up: "Signature not required: ...". Their "To sign" task disappears, and the signing page says "Your signature is not required". If the skipped person is you, you get no notification.
- In the card's steps the person is shown as "signature not required, skipped on ...". The route moves on or completes: "Everyone has signed. You can build the package."
- The skipped person's mark is not drawn on the document page. If electronic signatures already sit over the frozen PDF and the mark is printed in it, the mark stays: signatures must not be broken. The confirmation window warns about this, and the package guide marks it as not required. If there are no electronic signatures over the PDF yet, Studio freezes the document again without the mark, and signers who have not signed will open the new version.
- The action is written to the audit log (`signing_route.skip`), and the mail log gets a row for the email to the skipped person.
- The package does not wait for the skipped signature: the package check does not block on it. In the `КАК_ПРОВЕРИТЬ.txt` guide the document has the line "not required (skipped by the author)" (in a Russian-language project: «не требуется (пропущено автором)»). An optional signature that nobody placed and nobody skipped does not block the package either: Studio warns "Optional signature "..." in "..." is not placed" and writes "not signed (optional)" there. As before, the guide goes into the package only together with electronic signatures.

**Bring a skipped person back.** There is no separate button: a skip is undone by a new send. Clear the "Signature optional" mark on the signature (the skipped person's row shows "Returns to the route on the next send") and press "Send again" or "Send a new version". The person gets a request in their turn. While the mark stays, a new send keeps the skip.

**What you cannot do.**

- You cannot skip through MCP, there is no tool for it: a skip cancels the signature requirement and emails a third person, so it is the author's decision in the interface. An agent can only read that a signature is optional, who can be skipped, and the hint `skip_hint`: "The route author can skip them in the interface" ([MCP](mcp.md)).
- There is no automatic skipping: not by deadline, not by any other condition. Only the author's action.
- You cannot skip when the route is not running (stopped, returned, completed, cancelled) or when the person has no remaining signatures.
- You cannot skip a step that is not in the route yet: to add the person to the route later, send again.

## Signing date { #dates }

Templates often have a date line next to a signature, for example “« ___ » ________ 20__”. The Studio can fill in the day the person signed. A signature has date marks for that: frames on the page where the date is printed.

**Where to add them.** Date marks go where the signature is set up: on a document's “Signatures” tab for each signature, and in the route editor under “Where the signatures go”. Click “Add date”: a dashed “Date: …” frame appears under the signature frame on the open page. Drag it into place and pull its corner to size it. The frame can sit on any page of the document, not only next to the signature: “Here” moves it to the open page, “Go to” scrolls to it. “Remove date” deletes the mark. A signature can have up to 8 marks in a document.

**Format.** Each mark has its own “Format”; the list shows today as an example next to each name:

| Format | What it prints |
|---|---|
| Day | the day without a leading zero: 3, 13 |
| Month in words | November |
| Month as a number | two digits: 03, 11 |
| Year | 2026 |
| Two-digit year | 26 |
| Date | DD.MM.YYYY |
| Date in words | the day, the month in words and the year |

The month follows the document's language: a Russian document gets «ноября». “Alignment” puts the text at the left, center or right of the frame. The font size follows the frame height. If the text does not fit even in a small font, the panel warns “The text does not fit the frame”. If the mark's page is not in the document (say, after a template update), the panel says “The document has no page N: the date will not reach the PDF”.

**Example: «« 13 » ноября 2026 г.».** A Russian template already has the quotes, the line and “20” printed. Put three marks:

1. “Day” between the quotes;
2. “Month in words” on the line;
3. “Two-digit year” right after “20”.

The marks print with no frame and no background, over the template's line. You get «« 13 » ноября 2026 г.» with the day the person signed.

**Where the date comes from.**

- For a signature in the route it is the day the person approved the document. Until they approve, the marks are empty and the panel says “The date appears when … signs”, after the approval “The date comes from the approval in the signing route”. If the person approved before you added the marks, the date still appears: the Studio takes it from their approval. You cannot set the date by hand for such a signature.
- For a signature outside a route (you uploaded the image yourself), set the day in the “Signing date” field under the marks. While it is empty the marks stay empty (“Without a date the marks stay empty”), and the document is submitted without a date.
- A skipped signature gets no date.

The day is counted in Moscow time: an approval at 00:30 Moscow time gives that day, not the day before.

**Electronic signatures and the date.** The date mark is printed in the final PDF, and an electronic signature goes over the finished PDF. So the page shows the approval date, not the time of the electronic signature itself. The package guide (`HOW_TO_VERIFY.txt`, `КАК_ПРОВЕРИТЬ.txt` in a Russian project) has two lines for such a signature: “date on the page: …” and “signing time: …”.

Because of that, a date mark can add a step for an e-signature signer. The final PDF is frozen once every visible signature and date is on it, and the date appears only after the approval. If someone after that signer still adds a visible signature, the signer approves first and signs the final PDF as a second action. In the route editor their signature shows the hint “A signing date adds a step for an e-signature signer: approval before freezing”, and the steps show “2 actions” for them ([How many actions each person has](#actions)). If they are the last to add a visible signature, they still approve and sign with one click.

**Marks on a running or completed route.** You can add marks after sending too, for example if the supervisor has already signed the project proposal and the date line was forgotten. On a document held by a route (running or completed) the other signature settings are locked, but whoever manages the route (owner and editor) can edit the date marks. The route does not stop, and its history shows “changed the date marks”.

- If there are no electronic signatures over the final PDF yet, nothing is reset: the date simply appears in the document, and the final PDF is frozen again if needed.
- If electronic signatures are already over the final PDF, a new mark changes that PDF and those signatures have to be made again. The “Save the dates?” dialog names whose signatures are reset, for example “These signatures will be reset: Petrov P. P. The document will be frozen again and they will sign the final PDF once more. Save?”. “Cancel” changes nothing. After “Save” the document is frozen again, the owners of the reset signatures get the “Sign the final PDF” request, and a completed route runs again until they sign.

A stopped, returned or cancelled route does not hold the marks: they are saved as usual, and the next sending takes them into account.

Over MCP date marks are read-only ([MCP](mcp.md)).

## Routes sent earlier { #migration }

A route sent on an earlier Studio version had no version for signing yet. The Studio restores it on its own the first time it checks such a route:

- if the current build matches the one that was sent, it becomes the version for signing;
- otherwise the Studio looks for the same PDF among the document's recent builds.

If the version is found, the route goes on and the signers notice nothing. If not, a running route stops, and the card says “The version sent for signing cannot be restored: send a new version.” Click “Send new version”: the current build becomes the version for signing, and the signers approve it again in order.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/kp/submit/cp/topic-approval</span></div>
    <img src="../assets/shots/signing-migration.en.light.webp#only-light" alt="The version cannot be restored">
    <img src="../assets/shots/signing-migration.en.dark.webp#only-dark" alt="The version cannot be restored">
  </div>
  <figcaption>a route from an earlier Studio version whose sent version cannot be restored</figcaption>
</figure>

A route that an earlier Studio version stopped because of a rebuild (“The document changed after approval: the route is stopped.”) stays stopped. Its button is also “Send new version”.

## Questions and answers { #faq }

- **The server has no email.** Requests and reminders still arrive in the Inbox, on the “To sign” tab; there are no emails. Send the person the link yourself with “Copy link” on the card. If they have not accepted the invitation yet, the button makes a new invitation link and the previous one stops working. Automatic reminders do not go to an invitee without an account.
- **The supervisor has no account.** Invite them by email from the route with “Invite”. Using the invitation link they sign up with that same address, click “Accept” and land on the signing page. If registration on the server is closed, first ask the administrator to create an account for them.
- **The supervisor's image is gone after cancelling the route.** The route hides a signer's image until they approve, and cancelling does not reveal it. On the document's “Signatures” tab such a signature is marked “Held back by the route”. If you still want to put the image in without approval, click “Show” there and confirm: anyone who can edit signature placements can do it, and it goes to the audit log. While a route is running the button is unavailable. If you send the route again, the image is hidden again until approval.
- **The order is wrong.** While the route is not sent, drag the steps. If it is already sent, click “Cancel route”, fix the order on the route screen and click “Send again”. Approvals of documents that did not change are kept.
- **A signer left the project.** The route stops with “A participant left the project: assign someone else and send again”. Open the route, pick or invite another person with the same persona and click “Send again”. A route that is already completed does not care: the signatures are in place.
- **The “out for signing” banner.** The document was sent for signing and the route is running. You can edit the text and build: the route does not stop, it signs the version taken at sending. The signatures of this document cannot be changed on the “Signatures” tab: cancel the route on the checkpoint page first.
- **You found a typo while the document is being signed.** Fix and build the document. The route goes on with the old version. When you are ready, click “Send new version”: only this document is approved again, the other signatures stay.
- **You edited the text after everyone signed.** The signed version does not disappear: the package is built from it with a warning. If you need the corrected text, send a new version, and the changed document is signed again.
- **You rebuilt without edits, and the card shows changes.** This happens with documents from Word or PowerPoint: their PDF differs on every build. If the text did not change, you do not need to send a new version. With LaTeX documents this could happen when a runner older than 0.27.0 built them: a document without hyperlinks, such as the topic application, rebuilt in a different minute got a different PDF. A runner 0.27.0 or newer builds such a document byte for byte the same.
- **A document is replaced with your own PDF, and the signature is already inside the file.** The Studio signs the uploaded PDF but does not see signatures inside it: the route waits for a signature in the slot. Upload the signature as an image or sign on the signing page.
- **A document has to be signed from the current build without a route.** On the document's “Signatures” tab click “Sign the current build”. Signatures on the old version will no longer match the document.
- **In a local Studio.** There are no routes there, but the version for signing arrives with the project through git sync. The “Signatures” tab says “Being signed: the version of … (route on the server)”. Local edits and builds do not stop the server route.
- **“Sign the submission” says “The document is on a signing route”.** Route documents are signed only in turn, on the signing page. Click “Open the signing page” in the submission dialog.

## For the administrator { #admin }

Route emails go out only when email is configured ([Server emails](../deploy/mail.md)). What a signer can do with an electronic signature depends on whether keys may be stored on the server (admin, “Signing keys”): without that, CryptoPro and a ready signature file remain.

| Variable | Default | Meaning |
|---|---|---|
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_INTERVAL_S` | `900` | how often the server checks whom to remind, in seconds |
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_BEFORE_DEADLINE_HOURS` | `24` | how many hours before the deadline the reminder goes out |
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_WAITING_DAYS` | `3` | after how many days of waiting the reminder goes out |
| `HSE_STUDIO__SIGNING_ROUTE__REMINDER_MAX_AUTO` | `3` | how many automatic reminders a person gets per sending; `0` turns them off |
| `HSE_STUDIO__SIGNING_ROUTE__SWEEP_INTERVAL_S` | `300` | how often the server checks running routes against the documents, in seconds |

Signature places on the template lines work on the server only when a runner 0.27.0 or newer built the document: an older runner does not send the lines ([Runners](../deploy/runners.md#runner-version)).

The manual “Remind” is limited to once every 12 hours per person, and this is not configurable. All settings: [Environment variables](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md).
