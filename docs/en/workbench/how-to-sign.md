---
title: How to sign
description: For supervisors and academic supervisors. Where to find documents to sign, how to approve, sign with an image or an electronic signature and return for revision, including from a phone.
tags:
  - Workbench
  - Signatures
---

# How to sign

<p class="hds-lede">A student has sent you documents for signing. Everything happens on one page: look at the PDF, approve and add your signature. You do not have to set anything up in the project.</p>

This page is for supervisors. How a student sends the documents is described in [Send for signing](send-for-signing.md).

## Where to find the request { #request }

- **An email** “… asks you to sign: …” with an “Open the signing page” button, if the server sends email. The page opens after you sign in to your account, so a forwarded email does not let anyone sign for you.
- **The Inbox, “To sign” tab**: everything waiting for you, across all projects. Each task shows the checkpoint, the project, who asks, what is needed (“Approve”, “Approve and sign”, “Sign the final PDF”) and the deadline. Overdue tasks come first and are marked red. “Open” takes you to the signing page.
- **The bell** in the header shows “Waiting for your signature: N”, which leads to the same tab.
- **In the project**: on the checkpoint page, the “Signing” card has a “Go to signing” button.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/inbox?tab=signing</span></div>
    <img src="../assets/shots/signing-inbox.en.light.webp#only-light" alt="Inbox, To sign">
    <img src="../assets/shots/signing-inbox.en.dark.webp#only-dark" alt="Inbox, To sign">
  </div>
  <figcaption>the Inbox “To sign” tab and the bell with the “Waiting for your signature” row</figcaption>
</figure>

If you do not have an account on the server yet, a project invitation comes first. Sign up with the address it was sent to, click “Accept”, and the Studio opens the signing page right away. If you already have an account, the invitation arrives in the Inbox: click “Accept”. If it is already your turn, the Studio opens the signing page right away. If not, the documents appear on the “To sign” tab when your turn comes, and you get a notification. More: [Invitations and access requests](../deploy/invitations.md#accept).

## The signing page { #page }

- **The header**: who asks, when it was sent, the deadline, the “Message from the author” and an “Open project” link.
- **“Signing progress”**: the steps in order and each person's state. You are marked “You”.
- **What is needed from you**: for example “Your turn: approve the documents” or “Not your turn yet”. If your turn has not come, wait for the notification, there is nothing to do now.
- **“Documents”**: document tabs and the PDF. Above each document is the line “You are signing the version of …”: the version the author sent for signing. “Go to signature” scrolls to your frame, “Open PDF” opens the whole file. “Your signatures” and “Other signatures” show what is already in place.
- **“How to sign”**: the signing method and everything it needs. You choose among the methods the checkpoint allows. An image and an electronic signature with a plate are offered only if the author placed your signature on the document page.
- **Buttons** at the bottom: the main one (“Approve”, “Approve and sign” or “Sign”) and “Return for revision”.
- **“History”**: who sent, approved, signed or returned, and when.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-page.en.light.webp#only-light" alt="Signing page">
    <img src="../assets/shots/signing-page.en.dark.webp#only-dark" alt="Signing page">
  </div>
  <figcaption>the signing page: who asks and the deadline, the author’s message, signing progress, the PDF and “How to sign”</figcaption>
</figure>

You always see and sign the version sent for signing. The author may keep editing the text, but those edits do not go into it, and you get no notifications about them. To have you sign the corrected text, the author sends a new version ([below](#new-version)).

To approve means to confirm that you have read this version and agree with it. If the document has no place for your signature, the page says so: “No signature in the document, approval only”. Then clicking “Approve” is enough.

## Sign with an image { #image }

1. In “How to sign”, choose the “Image” method if the checkpoint allows several.
2. Add your signature in one of these ways:
    - “Use the saved one”, if you saved a signature in your profile before;
    - “Draw”: sign with your finger or mouse, then “Done” (“Clear” starts over);
    - “Upload”: a file with your signature; the editor can remove the background and crop it.
3. Tick “Remember for other projects” to use the signature with one click next time.
4. Click “Approve”.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-image.en.light.webp#only-light" alt="Image signature">
    <img src="../assets/shots/signing-image.en.dark.webp#only-dark" alt="Image signature">
  </div>
  <figcaption>“Image”: the signature is drawn right on the page, the frame shows where it goes</figcaption>
</figure>

The image appears in the document only at the moment you approve; before that nobody sees it. After the click the page says who signs next.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-approved.en.light.webp#only-light" alt="After approving">
    <img src="../assets/shots/signing-approved.en.dark.webp#only-dark" alt="After approving">
  </div>
  <figcaption>after the last person on the route approves: “Everyone has signed”, nothing more is needed from you</figcaption>
</figure>

## Sign with an electronic signature { #esign }

An electronic signature goes on the final PDF, when all visible signatures are already in it. So there are two cases:

- **One action**: the documents are already frozen. “Approve and sign” approves and signs at once.
- **Two actions**: someone after you still adds a visible signature. Click “Approve” first. When the final PDF is ready, a “Sign the final PDF” request arrives; open the page again and click “Sign”.

Why it works this way is explained in [Send for signing](send-for-signing.md#how-it-goes).

### Plate details

While the documents are not frozen yet, the Studio needs the details for the electronic signature plate: who signs and with which certificate. If the page says “A key or certificate for the signature plate is needed”, choose one:

- “Use the key “…””, if you already have a key in the Studio;
- “Certificate from CryptoPro”;
- “Certificate or public key file”: `.cer`, `.crt`, `.pem` or an OpenPGP public key `.asc`.

You can keep the certificate in your signer profile (settings, “Signing certificates”); then the plate fills itself in other projects.

### Sign with

“Sign with” lists only what your server allows:

- **“Studio key”**: the server signs with your key. If you do not have a key yet, click “Create an OpenPGP key” (the name on the plate; email and password are optional) or “Import a key” (`.asc`, `.gpg`, `.p12`, `.pfx`). The Studio does not store the key password; it is asked when you sign.
- **“CryptoPro in the browser”**: the key stays on the token, you pick the certificate next, and CryptoPro asks for the PIN. You need CryptoPro CSP, the CryptoPro Browser plug-in and the Chrome or Edge extension on a computer. More: [token e-signature](submit.md#cryptopro).
- **“Ready signature”**: click “Download PDF”, sign the file on your side (CryptoARM, CryptoPro, gpg) and upload the signature with “Choose signature”: `.asc`, `.sig` or `.p7s`, one per document. If the documents are not frozen yet, the page says “The final PDF appears after you approve”: approve first, you sign the file in the next step.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-esign.en.light.webp#only-light" alt="Electronic signature">
    <img src="../assets/shots/signing-esign.en.dark.webp#only-dark" alt="Electronic signature">
  </div>
  <figcaption>“Detached e-signature”: your frame on the page, “Sign with” and “Approve and sign”</figcaption>
</figure>

If the server does not store private keys, the page says so: you cannot create or import a key; sign with CryptoPro or upload a ready signature. The “E-signature in the PDF” method works only with a Studio key, so on such a server you cannot choose it: pick another method or return the documents to the author.

## Approval date { #date }

If the author added date marks to your signature, the signing page labels their frames “Approval date”. You do not need to do anything with them: when you click “Approve” or “Approve and sign”, the Studio fills in the day of your approval in Moscow time, for example «« 13 » ноября 2026 г.» in a Russian document.

- The date comes from the approval, not from the time of the electronic signature. If you sign with an electronic signature, the page shows the approval day, and the time of the signature itself is in the package guide (`HOW_TO_VERIFY.txt`, `КАК_ПРОВЕРИТЬ.txt` in a Russian project).
- With a date mark an electronic signature sometimes takes a second action: if someone after you still adds a visible signature, click “Approve” first, and on the “Sign the final PDF” request click “Sign”.
- If the author added a date mark after you had signed the final PDF with an electronic signature, the PDF changes and a new “Sign the final PDF” request arrives. You do not need to approve again, only sign the new file. The date on the page stays the day of your approval.

## Return for revision { #return }

If something in the document needs fixing, click “Return for revision”, write what exactly in “What to fix” (required, up to 2000 characters) and click “Return”. The author gets your comment and the route stops. When the author fixes it and sends it again, you get a notification.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-return.en.light.webp#only-light" alt="Return for revision">
    <img src="../assets/shots/signing-return.en.dark.webp#only-dark" alt="Return for revision">
  </div>
  <figcaption>the “Return for revision” dialog: a comment is required</figcaption>
</figure>

Detailed remarks on the text are easier to leave as comments in the project itself: the return dialog has an “Open project” link.

## A new version { #new-version }

If a document was fixed after sending, the author can send a new version. Then:

- If it is your turn now, you get the request “… asks you to sign a new version: …” (or “approve a new version”).
- If you already approved or signed the changed document but your turn has not come yet, the Inbox gets “A new version is out for signing: …”: the request comes in your turn. There is no email in this case.
- If the documents you sign did not change, nothing comes: your approvals and signatures stay.

At the top of the signing page you see what changed, for example “New version: the document “Topic selection application” has changed. Approve it again.” Below is the author's text from the “What changed” field, if they filled it in. In the email it is under “Message from the sender”. Unchanged documents are marked “No changes: you already approved” or “No changes: you already signed”: there is nothing to do for them.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-version-page.en.light.webp#only-light" alt="A new version">
    <img src="../assets/shots/signing-version-page.en.dark.webp#only-dark" alt="A new version">
  </div>
  <figcaption>a new version: what changed, the author's message and “You are signing the version of …”</figcaption>
</figure>

Your image and key are kept, so approving again is one click. If you add an electronic signature, it has to be made again on a changed document: the old one belonged to the old version.

If you are the route's author or manage it, the signing page also shows you what signers do not see: “There are changes after sending for signing. The version of … is being signed.” and the “Send new version” button.

## If the document changed { #changed }

- “The document changed while the page was open”: while you were looking, the author sent a new version. Look at it and click the button again.
- “The document changed after you approved it: please approve again”: the author sent a new version of this document. Your image and key are still there, so this is one click.
- “Route stopped”: the author is changing the signers, the documents were returned for revision, or signatures changed outside the route. There is nothing to do; you will be notified when the author sends it again.
- “Signing page not found”: the route is closed, the link is out of date, or you are signed in to another account. Open the Inbox and check the “To sign” tab.

## If your signature is not required { #skipped }

Until the author skips you, you sign as usual. A signature place the author marked optional has the note "optional" on the page: you can sign it, but the route will not wait for it.

If the author decides your signature is not needed at this checkpoint, they press "Skip". Then:

- you get an inbox notification and an email: "Signature not required: ...". The task disappears from the "To sign" tab;
- the signing page says "Your signature is not required. The route author skipped your step. There is nothing to do.";
- your earlier approvals and signatures on other places stay.

If the author sends the route again and clears the "optional" mark, you get a request again in your turn.

## From a phone { #phone }

The signing page works in a phone browser, and the buttons stick to the bottom of the screen.

- Signing with an image is easy right with your finger: “Draw”.
- You can sign with a Studio key from a phone too.
- There is no CryptoPro on a phone: the browser plug-in exists only on a computer.
- You can upload a ready signature if the signature file is on your phone.

<figure class="hds-fig" style="max-width: 22rem">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/sign/kp/…</span></div>
    <img src="../assets/shots/signing-phone.en.light.webp#only-light" alt="From a phone">
    <img src="../assets/shots/signing-phone.en.dark.webp#only-dark" alt="From a phone">
  </div>
  <figcaption>on a phone: the buttons at the bottom of the screen</figcaption>
</figure>

What else works on a phone: [Mobile version](../start/mobile.md).
