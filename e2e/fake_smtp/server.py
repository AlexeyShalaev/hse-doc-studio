"""Поддельный SMTP-сервер для e2e журнала писем (только стандартная библиотека).

SMTP (порт FAKE_SMTP_PORT, по умолчанию 2525, без TLS): EHLO, HELO, AUTH PLAIN и LOGIN, MAIL, RCPT, DATA, RSET,
NOOP, VRFY, QUIT. Любые логин и пароль принимаются, пока не включён отказ входа: тогда AUTH отвечает 535 и
повторяет логин в тексте ответа (так тест видит, что Студия прячет его в журнале). Получатель `reject-*@...` получает
550, `busy-*@...` получает 451, остальные письма принимаются и складываются в память.

HTTP (порт FAKE_SMTP_HTTP_PORT, по умолчанию 8025):
- `GET /messages` и `GET /messages?to=<адрес>`: пойманные письма, новые последними;
- `DELETE /messages`: забыть все письма;
- `GET /config`, `POST /config` с `{"auth_fail": true}`: отказ входа 535 включается и выключается без перезапуска;
- `GET /health`.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import socketserver
import threading
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

HOSTNAME = "fake-smtp"
MAX_MESSAGES = 1000
MAX_LINE = 64 * 1024

_LOCK = threading.Lock()
_MESSAGES: list[dict[str, Any]] = []
_CONFIG = {"auth_fail": os.environ.get("FAKE_SMTP_AUTH_FAIL", "") in ("1", "true")}
_SEQ = [0]


def _address(arg: str) -> str:
    """`FROM:<a@b> BODY=8BITMIME` или `TO:<a@b>` в адрес без угловых скобок."""
    _, _, rest = arg.partition(":")
    rest = rest.strip()
    if rest.startswith("<"):
        return rest[1 : rest.find(">")] if ">" in rest else rest[1:]
    return rest.split(" ", 1)[0]


def _parts(message: Message) -> tuple[str | None, str | None]:
    if not isinstance(message, EmailMessage):
        return None, None
    text = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    return (
        text.get_content() if text is not None else None,  # type: ignore[attr-defined]
        html.get_content() if html is not None else None,  # type: ignore[attr-defined]
    )


def _store(mail_from: str, rcpt_to: list[str], raw: bytes) -> None:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    text, html = _parts(message)
    with _LOCK:
        _SEQ[0] += 1
        _MESSAGES.append(
            {
                "id": _SEQ[0],
                "received_at": datetime.now(UTC).isoformat(),
                "mail_from": mail_from,
                "rcpt_to": rcpt_to,
                "message_id": str(message.get("Message-ID", "")).strip(),
                "subject": str(message.get("Subject", "")),
                "to": str(message.get("To", "")),
                "text": text,
                "html": html,
            }
        )
        del _MESSAGES[:-MAX_MESSAGES]


class SmtpHandler(socketserver.StreamRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.mail_from: str | None = None
        self.rcpt_to: list[str] = []

    def reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")
        self.wfile.flush()

    def readline(self) -> str | None:
        raw = self.rfile.readline(MAX_LINE)
        if not raw:
            return None
        return raw.decode("utf-8", "replace").rstrip("\r\n")

    def reset(self) -> None:
        self.mail_from = None
        self.rcpt_to = []

    def handle(self) -> None:
        self.reply(f"220 {HOSTNAME} ESMTP fake")
        while True:
            line = self.readline()
            if line is None:
                return
            verb, _, arg = line.partition(" ")
            verb = verb.upper()
            if verb == "QUIT":
                self.reply("221 2.0.0 Bye")
                return
            handler = getattr(self, f"cmd_{verb.lower()}", None)
            if handler is None:
                self.reply("502 5.5.2 Command not recognized")
                continue
            handler(arg.strip())

    def cmd_ehlo(self, arg: str) -> None:
        self.reset()
        self.reply(f"250-{HOSTNAME} greets {arg or 'client'}")
        self.reply("250-8BITMIME")
        self.reply("250-SMTPUTF8")
        self.reply("250-SIZE 10485760")
        self.reply("250 AUTH PLAIN LOGIN")

    def cmd_helo(self, arg: str) -> None:
        self.reset()
        self.reply(f"250 {HOSTNAME} greets {arg or 'client'}")

    def cmd_noop(self, _arg: str) -> None:
        self.reply("250 2.0.0 OK")

    def cmd_rset(self, _arg: str) -> None:
        self.reset()
        self.reply("250 2.0.0 OK")

    def cmd_vrfy(self, _arg: str) -> None:
        self.reply("252 2.1.5 Cannot VRFY user")

    def cmd_starttls(self, _arg: str) -> None:
        self.reply("454 4.7.0 TLS not available")

    def cmd_auth(self, arg: str) -> None:
        mechanism, _, initial = arg.partition(" ")
        mechanism = mechanism.upper()
        try:
            if mechanism == "PLAIN":
                if not initial:
                    self.reply("334 ")
                    initial = self.readline() or ""
                _, user, _password = base64.b64decode(initial).decode("utf-8", "replace").split("\0", 2)
            elif mechanism == "LOGIN":
                if initial:
                    user = base64.b64decode(initial).decode("utf-8", "replace")
                else:
                    self.reply("334 VXNlcm5hbWU6")
                    user = base64.b64decode(self.readline() or "").decode("utf-8", "replace")
                self.reply("334 UGFzc3dvcmQ6")
                base64.b64decode(self.readline() or "")
            else:
                self.reply("504 5.5.4 Unrecognized authentication type")
                return
        except (ValueError, binascii.Error):
            self.reply("501 5.5.2 Cannot decode response")
            return
        with _LOCK:
            fail = _CONFIG["auth_fail"]
        if fail:
            self.reply(f"535 5.7.8 Authentication credentials invalid for {user}")
            return
        self.reply("235 2.7.0 Authentication successful")

    def cmd_mail(self, arg: str) -> None:
        self.reset()
        self.mail_from = _address(arg)
        self.reply("250 2.1.0 OK")

    def cmd_rcpt(self, arg: str) -> None:
        if self.mail_from is None:
            self.reply("503 5.5.1 Need MAIL first")
            return
        address = _address(arg)
        local = address.partition("@")[0].lower()
        if local.startswith("reject-"):
            self.reply(f"550 5.1.1 <{address}>: Recipient address rejected: User unknown")
            return
        if local.startswith("busy-"):
            self.reply(f"451 4.3.0 <{address}>: Mailbox busy, try again later")
            return
        self.rcpt_to.append(address)
        self.reply("250 2.1.5 OK")

    def cmd_data(self, _arg: str) -> None:
        if self.mail_from is None or not self.rcpt_to:
            self.reply("503 5.5.1 Need RCPT first")
            return
        self.reply("354 End data with <CR><LF>.<CR><LF>")
        lines: list[bytes] = []
        while True:
            raw = self.rfile.readline(MAX_LINE)
            if not raw:
                return
            if raw in (b".\r\n", b".\n"):
                break
            # Снятие точки (RFC 5321, 4.5.2): строка, начатая точкой, приходит с лишней точкой впереди.
            lines.append(raw[1:] if raw.startswith(b"..") else raw)
        _store(self.mail_from, list(self.rcpt_to), b"".join(lines))
        self.reset()
        self.reply("250 2.0.0 OK: queued")


class SmtpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class HttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: ARG002
        return

    def _json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        if url.path == "/health":
            self._json(200, {"ok": True})
            return
        if url.path == "/config":
            with _LOCK:
                self._json(200, dict(_CONFIG))
            return
        if url.path == "/messages":
            to = (parse_qs(url.query).get("to") or [""])[0].lower()
            with _LOCK:
                found = [m for m in _MESSAGES if not to or to in (r.lower() for r in m["rcpt_to"])]
            self._json(200, found)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/config":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        with _LOCK:
            if "auth_fail" in body:
                _CONFIG["auth_fail"] = bool(body["auth_fail"])
            self._json(200, dict(_CONFIG))

    def do_DELETE(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/messages":
            self._json(404, {"error": "not found"})
            return
        with _LOCK:
            _MESSAGES.clear()
        self._json(200, {"ok": True})


def main() -> None:
    smtp_port = int(os.environ.get("FAKE_SMTP_PORT", "2525"))
    http_port = int(os.environ.get("FAKE_SMTP_HTTP_PORT", "8025"))
    # Сервер только во внутренней сети стенда, HTTP опубликован на loopback хоста.
    smtp = SmtpServer(("0.0.0.0", smtp_port), SmtpHandler)  # noqa: S104
    threading.Thread(target=smtp.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", http_port), HttpHandler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
