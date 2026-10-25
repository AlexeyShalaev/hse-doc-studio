---
title: Submission and packaging
description: Submission profiles from the template, the readiness ring, forms, signatures and packaging archives with canonical names.
tags:
  - Workbench
  - Submission
  - Signatures
---

# Submission and packaging

<p class="hds-lede">Submission mode gathers everything needed to hand the work in: the submission profiles from the template, forms, signatures and packaging an archive with canonical file names.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/projects/vkr/submit</span></div>
    <img src="../assets/shots/submit.en.light.png#only-light" alt="Submission point">
    <img src="../assets/shots/submit.en.dark.png#only-dark" alt="Submission point">
  </div>
  <figcaption>a submission point: the readiness ring, documents, signatures and forms</figcaption>
</figure>


## Submission profiles { #checkpoints }

A submission profile is a package composition declared by the template: which documents, forms and signatures a particular submission needs.

- **The readiness ring** “N of M ready” on every profile; “Pin” it — and badges across the Workbench count blockers towards that profile.
- **Item statuses** — “built”, “not built”, “with errors”, signed or not; “Open document” goes off to fix it.
- **“Package”** — an archive (zip, tar.gz and more) with canonical names: “Technical specification.pdf”, not `technical_specification.pdf`; preflight checks run before packaging.
- **“Past builds”** — package history: contents, “Download”, “Copy path”.

Each template's profile composition is in the [reference](../reference/checkpoints.md).

## Forms { #forms }

Forms are declared by the template — for example, an AI usage declaration. The Studio renders the form, shows a live preview and produces the official PDF from your answers; the status is visible in Submission and in the “Now” block.

## Signatures { #signatures }

- **The signature library** — one PNG per slot (author, supervisor…) for the whole project; a built-in editor: “Remove background”, eraser, crop, ink colour.
- **Placement** — drag the signature to the right spot on the document page, with a date if needed.
- **Stamping** — at packaging time and via the “With signatures” download the PNG is stamped into the PDF; there is a cryptographic layer too — a PAdES electronic signature with a certificate from Settings.

### Detached electronic signature { #detached-signatures }

For documents signed with an enhanced electronic signature or through GnuPG (a topic application, a statement), a signature slot has a second type: “Detached e-signature”. Instead of a picture, the PDF carries the caption “Signed with a detached electronic signature”, and the signature itself is attached to the document as a separate file.

1. On the document's “Signatures” tab switch the slot to “Detached e-signature”, enable it and place the caption frame (with a date if you want).
2. **“Freeze PDF for signing”**: the Studio makes a copy of the PDF with the caption and shows its SHA-256. The signatures cover exactly those bytes. After the document is rebuilt the signatures are marked invalid and the freeze has to be repeated.
3. Attach a signature in one of three ways:
    - **upload a ready file**: `.asc` or `.sig` (OpenPGP) and `.sig` or `.p7s` (CMS/CAdES, including GOST R 34.10-2012 from CryptoARM and CryptoPro). The format is detected automatically; you can drop the file on the slot. The Studio shows the signer (name, CA, certificate validity, algorithm) and checks the signature against the frozen PDF. For OpenPGP with an unknown key it asks for the signer's public key;
    - **sign in the Studio**: with an OpenPGP key or a `.p12` certificate from “Settings → Signatures”. A key can be created right in the signing window, the name comes from the project;
    - **send for signing**: “Files for the signer (zip)” holds the PDF, its SHA-256 and instructions; the supervisor returns the signature file.
4. The submission package gets the frozen PDF unchanged, one signature file per signer, the OpenPGP public keys and a README with verification commands. A package with such a slot is not built without an attached signature.

What is checked and what is not: file integrity and the signature itself (RSA, ECDSA, GOST R 34.10-2012 with Streebog, OpenPGP), the certificate validity at signing time. The chain to a CA root counts as trusted only after the root certificate is added in “Settings → Signatures”. Revocation lists (CRL, OCSP) are not checked. A qualified signature on a token cannot be made inside the Studio: sign the file in CryptoARM or CryptoPro and upload the result.

## Requirements { #requirements }

The traceability matrix: every requirement from the specification (`\req{…}`) and where it is referenced (`\reqref{…}`) — the “covered / not referenced” statuses expose gaps before the committee finds them. The recognition format is configurable, and “Suggest with AI” proposes one from your text.

## Team projects

Submission computes readiness for one author at a time: pick whose package to build — the ring, blockers and archive recompute. Shared documents enter every author's package.
