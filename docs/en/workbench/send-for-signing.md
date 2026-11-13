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
- A template update plan shows the same line if the update touches documents out for signing.
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
- A LaTeX document rebuilt without edits gives the same PDF, so there is no mark. A document from Word or PowerPoint comes out different on every rebuild, so after any rebuild the card shows changes. You do not have to send a new version in that case.

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
- **You rebuilt without edits, and the card shows changes.** This happens with documents from Word or PowerPoint: their PDF differs on every build. If the text did not change, you do not need to send a new version.
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

The manual “Remind” is limited to once every 12 hours per person, and this is not configurable. All settings: [Environment variables](https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/docs/ru/deploy/env-reference.md).
