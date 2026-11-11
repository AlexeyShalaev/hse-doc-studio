---
title: Server emails
description: Which emails the Studio sends, in which language, how they are built, how to preview them in the admin area, the log of sent emails and export to files.
tags:
  - Deployment
  - Mail
---

# Server emails

<p class="hds-lede">The Studio sends emails in one design: a heading, the point in one sentence, a button or a code, the reason you got the email, a security block and the server address. An email goes out in the language of the recipient's account, in two parts: plain text and HTML.</p>

Without SMTP no emails are sent and the links are shown on screen. SMTP setup is described in [People and sign-in](accounts.md). Every attempt to send an email, successful or not, is visible in the [mail log](#mail-log).

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
| Signing route: request to sign | it is the signer's turn on a “Send for signing” route | who asks, project, checkpoint, deadline, “Open the signing page” button |
| Signing route: sign the final PDF | the documents are frozen, only the signer's electronic signature is left | project, checkpoint, deadline, “Open the signing page” button |
| Signing route: reminder | the author pressed “Remind” or the deadline is near | the same as the request to sign |
| Signing route: returned for revision | a signer returned the documents; only the route author gets the email | who returned, the comment, “Open the checkpoint” button |
| Signing route: everyone has signed | the route is complete; only the route author gets the email | project, checkpoint, “Open the checkpoint” button |
| Test email | the “Send” button in the “Mail (SMTP)” block | confirmation that sending works |

Links in signing route emails carry no tokens: the signing page opens only after sign-in, so a forwarded email does not let anyone sign. Other route events (stopped, cancelled) arrive only in the Inbox. How a route goes: [Send for signing](../workbench/send-for-signing.md) and [How to sign](../workbench/how-to-sign.md).

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

## Mail log { #mail-log }

Admin area, the **Mail** section (`/admin/mail`, the “Log” group): every attempt to send an email in one row. The section answers the support question “the email never arrived”: whether it was sent at all, to which address and what the SMTP server replied. How to read the section and what to do about each result is in the administrator help on the Studio server, the “Mail” article (`/help/en/admin/mail/`).

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/admin/mail</span></div>
    <img src="../assets/shots/mail-log.en.light.webp#only-light" alt="The Mail section">
    <img src="../assets/shots/mail-log.en.dark.webp#only-dark" alt="The Mail section">
  </div>
  <figcaption>the mail log: the last 24 hours strip, filters and the result of every attempt</figcaption>
</figure>

- **Results.** “Sent”: the SMTP server accepted the email. “Failed”: the server refused, dropped the connection or did not answer. “Not sent”: mail is not set up, or the email was not due (the recipient’s address is not confirmed, sign-in is blocked). The log does not see delivery after the SMTP server (a mailbox refusal, spam).
- **No retries.** An email is sent in a single attempt at the moment of the action; there is no mail queue. A failed email does not go out by itself after a restart or after SMTP is fixed: the log keeps a “Failed” row with the reason, and the action has to be repeated (a new reset link, a resent invitation). Project and signing route notifications stay in the Inbox anyway.
- **Coverage.** Every email from the table above, the test email included, goes through one sending point, and that point writes the log.
- **No links, no messages.** The email body, token links and people’s messages are not stored. The email card redraws the email with the current template from the stored values: “\[link hidden\]” stands in place of the link, “\[message not kept in the log\]” in place of a message. If the template changed since sending, the card says so.
- **Access.** Only the installation administrator, with a browser session; a personal access token does not work. Reading the log is not audited, and a row cannot be deleted manually.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/admin/mail</span></div>
    <img src="../assets/shots/mail-log-card.en.light.webp#only-light" alt="The email card">
    <img src="../assets/shots/mail-log-card.en.dark.webp#only-dark" alt="The email card">
  </div>
  <figcaption>the email card: the reason and SMTP reply, details, the email with its link hidden</figcaption>
</figure>

If the SMTP server rejects the sign-in, does not answer or fails to set up a secure connection, a hint with a link to the “Mail (SMTP)” block appears under the last 24 hours strip. Without mail the section shows the “Mail is not set up” banner at the top.

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/admin/mail</span></div>
    <img src="../assets/shots/mail-log-smtp-auth.en.light.webp#only-light" alt="The SMTP server rejects the sign-in">
    <img src="../assets/shots/mail-log-smtp-auth.en.dark.webp#only-dark" alt="The SMTP server rejects the sign-in">
  </div>
  <figcaption>the SMTP server rejects the sign-in: the hint under the strip and “Failed” rows with code 535</figcaption>
</figure>

### The `mail_log` table

One row per attempt, about 1 KB. It holds the time and duration of the attempt, the email type (`template`) and language, the address (`to_email`) and the installation user (`to_user_id`), the subject, the result (`status`: `sent`, `failed`, `not_sent`, `suppressed`) and reason (`reason`), the SMTP reply code and text (up to 300 characters, the SMTP username and password cut out), `message_id`, the number of attempts (always 1 today), what triggered the email (`cause`: `user`, `anonymous`, `system`, plus `actor_user_id` or the background task name), the scenario (`origin`), the request `request_id`, the project and object (route, invitation), the safe template values (`params`: names, project title, role, link expiry) and the template fingerprint. `request_id` finds the row in the api logs, `message_id` finds the email in the mail server logs.

The row is written after the SMTP server replies, in its own short transaction. Rolling back the action that caused the email does not erase the fact of sending, and a log write failure breaks neither the sending nor the action: it shows only in the api log and in the `hse_mail_log_write_failures_total` metric.

The application uses the table with the schema owner role, like every other table. If you gave the application a separate Postgres role, it needs `SELECT`, `INSERT`, `DELETE` and `UPDATE (actor_user_id)` on `mail_log` and `USAGE` on `mail_log_id_seq`.

### Retention

90 days by default, 14 to 730: admin area, **Data retention**, the “Mail log” source ([Autonomous operation and data retention](autonomy.md)). The scheduled cleanup removes old rows in batches; the source is included in both **Clean now** and **Free up space**.

### Metrics

In `/metrics` (with the `HSE_STUDIO__OBSERVABILITY__METRICS_TOKEN` token):

| Metric | What it counts |
|---|---|
| `hse_mail_sent_total{kind,status}` | attempts to send an email: `kind` is the email type, `status` the result (`sent`, `failed`, `not_sent`, `suppressed`). A series appears with the first attempt of that pair. |
| `hse_mail_log_write_failures_total` | log rows that could not be written. Always present, even at zero. |

The counters live in the api process and reset on restart: with several instances, sum over all of them. Example alerts: `sum(increase(hse_mail_sent_total{status="failed"}[1h])) > 0` and `sum(increase(hse_mail_log_write_failures_total[1h])) > 0`.

### Deleting and exporting a person’s data

The recipient address and the names in the template values are personal data.

- **Deleting an account** (admin area, **Users**, **Delete permanently** on a disabled account) deletes the emails to that person: by their id and by any of their addresses, case-insensitively, including the email to the new address on an email change. In emails that the person triggered for other people the reference to them is cleared, while their name in the email text stays, as in the recipient’s Inbox.
- **Exporting one’s own data** (`GET /api/v1/account/export`, the `my-data.json` file) includes a `mail` section: the time, type, language, address, subject, result and reason of the emails to this person, up to the latest 5000. Template values and internal fields are not exported.

## Export all emails to files

For developers and anyone who wants to look at the emails in a browser:

```bash
cd services/api
uv run python scripts/render_mails.py mail-preview
```

The directory gets `<type>.<language>.html` and `.txt` for every email plus an `index.html` with the list. To check the dark theme and a narrow screen, switch them on in the browser developer tools.
