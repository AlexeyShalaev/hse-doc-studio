"""Локальные HTTP-серверы для тестов без обратного DNS.

`HTTPServer.server_bind` зовёт `socket.getfqdn(host)`, то есть `gethostbyaddr`. На раннерах
macOS и Windows обратный DNS для 127.0.0.1 может висеть десятки секунд и роняет тест по таймауту.
Серверу тестов имя хоста не нужно, поэтому привязка делается без него.
"""

from __future__ import annotations

import socketserver
from http.server import HTTPServer, ThreadingHTTPServer


class _NoFqdnBind:
    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)  # type: ignore[arg-type]
        host, port = self.server_address[:2]  # type: ignore[attr-defined]
        self.server_name = str(host)  # type: ignore[attr-defined]
        self.server_port = port  # type: ignore[attr-defined]


class LoopbackHTTPServer(_NoFqdnBind, HTTPServer):
    pass


class LoopbackThreadingHTTPServer(_NoFqdnBind, ThreadingHTTPServer):
    pass
