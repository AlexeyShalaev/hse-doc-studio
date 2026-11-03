---
title: Server emails
description: Which emails the Studio sends, in which language, how they are built, how to preview them in the admin area and export them to files.
tags:
  - Deployment
  - Mail
---

# Server emails

<p class="hds-lede">The Studio sends emails in one design: a heading, the point in one sentence, a button or a code, the reason you got the email, a security block and the server address. An email goes out in the language of the recipient's account, in two parts: plain text and HTML.</p>

Without SMTP nothing changes: no emails are sent and the links are shown on screen, as before. SMTP setup is described in [People and sign-in](accounts.md).

## Which emails are sent

| Email | When it is sent | Main block |
|---|---|---|
| Email confirmation | sign-up, resending the confirmation | button, the link is valid for 48 hours |
| Password reset | “Forgot password” | button, the link is valid for 1 hour |
| Invitation to the Studio | an administrator invited an address | button, the link is valid for 7 days (or the period the administrator chose) |
| Email change | a person changed the address in account settings | button to the new address, the link is valid for 48 hours |
| Password reset link issued | an administrator issued a reset link | notice without a link |
| Passkey added | a sign-in key was added to the account | notice, key name, button to account settings |
| Passkeys reset | an administrator removed all keys | notice, number of keys, button to account settings |
| Project invitation (to the Inbox) | a person who already has an account is invited | “Open Inbox” button |
| Project invitation (by link) | an address without an account is invited, resending | button with the invitation link, the inviter's message, expiry |
| Project access request | someone asks for access to a closed project | “Open Inbox” button |
| Project transfer | a project is being transferred to you | “Open Inbox” button |
| Test email | the “Send” button in the “Mail (SMTP)” block | confirmation that sending works |

The Studio does not send numeric confirmation codes today: every action is confirmed by a link. The template can show a code in a large monospace font with its validity period once such an email appears.

## Which language is used

1. The language of the recipient's account (the “language” profile field), if set.
2. Otherwise the interface language of the request. For an invitation to an address without an account this is the inviter's language.
3. Otherwise Russian.

The subject is localized the same way as the body. The texts live in `services/api/hse_doc_studio/core/mail/locales/ru.json` and `en.json`; a test keeps their keys and placeholders identical.

## How an email is built

- An email has two parts (`multipart/alternative`): plain text and HTML. A client without HTML shows the text, where the link stands on its own line.
- The HTML uses tables and inline styles, with no external fonts, scripts or images: the Studio mark is set in text, so the email looks the same even when the client blocks images.
- Light and dark themes: where the mail client reads `prefers-color-scheme`, the email switches to the Studio dark colors; other clients show the light version with enough contrast. On a narrow screen the button spans the full width.
- Every value (names, project titles, the inviter's message) is escaped. Subjects never get line breaks or control characters, and a long value is truncated.
- Links in an email point only to the public address of the server (`HSE_STUDIO__AUTH__PUBLIC_URL`). If it is not set, the email has no button and the link stays in the text only. Set the public address to make the emails usable.

## Preview emails in the admin area

Admin area, the **Sign-in and registration** section, the “How emails look” block (below the “Mail (SMTP)” block). Pick an email type and a language: the subject appears next to the picker, the email in a frame below it (as the recipient sees it) and the text part. The preview uses made-up data and sends nothing.

To see an email in your own inbox, press **Send** in the “Test email” row of the “Mail (SMTP)” block: it arrives in your account language.

## Export all emails to files

For developers and anyone who wants to look at the emails in a browser:

```bash
cd services/api
uv run python scripts/render_mails.py mail-preview
```

The directory gets `<type>.<language>.html` and `.txt` for every email plus an `index.html` with the list. To check the dark theme and a narrow screen, switch them on in the browser developer tools.
