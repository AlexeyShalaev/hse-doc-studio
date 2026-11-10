---
title: How to sign
description: For supervisors and academic supervisors. Where to find documents to sign, how to approve, sign with an image or an electronic signature and return for rework, including from a phone.
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

If you do not have an account on the server yet, a project invitation comes first. Sign up with the address it was sent to, click “Accept”, and the Studio opens the signing page right away. If you already have an account, the invitation arrives in the Inbox: accept it, and the documents appear on the “To sign” tab. More: [Invitations and access requests](../deploy/invitations.md#accept).

## The signing page { #page }

- **The header**: who asks, when it was sent, the deadline, the “Message from the author” and an “Open project” link.
- **“Signing progress”**: the steps in order and each person's state. You are marked “You”.
- **What is needed from you**: for example “Your turn: approve the documents” or “Not your turn yet”. If your turn has not come, wait for the notification, there is nothing to do now.
- **“Documents”**: document tabs and the PDF. “Go to signature” scrolls to your frame, “Open PDF” opens the whole file. “Your signatures” and “Other signatures” show what is already in place.
- **“How to sign”**: the signing method and everything it needs.
- **Buttons** at the bottom: the main one (“Approve”, “Approve and sign” or “Sign”) and “Return for rework”.
- **“History”**: who sent, approved, signed or returned, and when.

To approve means to confirm that you have read this version and agree with it. If the document has no place for your signature, the page says so: “No signature in the document, approval only”. Then clicking “Approve” is enough.

## Sign with an image { #image }

1. In “How to sign”, choose the “Image” method if the checkpoint allows several.
2. Add your signature in one of these ways:
    - “Use the saved one”, if you saved a signature in your profile before;
    - “Draw”: sign with your finger or mouse, then “Done” (“Clear” starts over);
    - “Upload”: a file with your signature; the editor can remove the background and crop it.
3. Tick “Remember for other projects” to use the signature with one click next time.
4. Click “Approve”.

The image appears in the document only at the moment you approve; before that nobody sees it. After the click the page says who signs next.

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

If the server does not store private keys, the page says so: you cannot create or import a key; sign with CryptoPro or upload a ready signature. The “E-signature in the PDF” method works only with a Studio key, so on such a server you cannot choose it: pick another method or return the documents to the author.

## Return for rework { #return }

If something in the document needs fixing, click “Return for rework”, write what exactly in “What to fix” (required, up to 2000 characters) and click “Return”. The author gets your comment and the route stops. When the author fixes it and sends it again, you get a notification.

Detailed remarks on the text are easier to leave as comments in the project itself: the return dialog has an “Open project” link.

## If the document changed { #changed }

- “The document changed while the page was open”: the author rebuilt the document in the meantime. Look at the new version and click the button again.
- “The document changed after you approved it: please approve again”: the author fixed the document and sent it again. Your image and key are still there, so this is one click.
- “Route stopped”: the author is editing the document or changing the signers. There is nothing to do; you will be notified when they send it again.
- “Signing page not found”: the route is closed, the link is out of date, or you are signed in to another account. Open the Inbox and check the “To sign” tab.

## From a phone { #phone }

The signing page works in a phone browser, and the buttons stick to the bottom of the screen.

- Signing with an image is easy right with your finger: “Draw”.
- You can sign with a Studio key from a phone too.
- There is no CryptoPro on a phone: the browser plug-in exists only on a computer.
- You can upload a ready signature if the signature file is on your phone.

What else works on a phone: [Mobile version](../start/mobile.md).
