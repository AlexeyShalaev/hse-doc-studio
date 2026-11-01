"""Поддельный OpenAI-совместимый сервер для живого стенда личных раннеров (только стандартная библиотека).

Модель выбирает режим ответа: `fake-model` отвечает словами по одному, `fake-slow` медленно (для отмены),
`fake-drop` рвёт соединение посреди ответа, `fake-500` отвечает ошибкой, `fake-huge` шлёт огромный ответ.
`GET /stats` считает запросы и соединения, закрытые клиентом посреди потока: так тест видит, что отмена
в чате дошла до модели через раннер.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = ("fake-model", "fake-slow", "fake-drop", "fake-500", "fake-huge")
WORDS = ("Привет", ", ", "это ", "модель ", "за ", "раннером", ".")
_STATS = {"requests": 0, "completed": 0, "client_closed": 0}
_LOCK = threading.Lock()


def _count(key: str) -> None:
    with _LOCK:
        _STATS[key] += 1


def _chunk(text: str, model: str, finish: str | None = None) -> bytes:
    body = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": text} if text else {}, "finish_reason": finish}],
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: ARG002
        return

    def _json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/stats":
            with _LOCK:
                self._json(200, dict(_STATS))
            return
        if self.path.rstrip("/") == "/v1/models":
            _count("requests")
            self._json(200, {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "e2e"} for m in MODELS]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        _count("requests")
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        model = str(request.get("model") or "fake-model")
        if model == "fake-500":
            self._json(500, {"error": {"message": "upstream exploded"}})
            return
        if not request.get("stream"):
            self._json(
                200,
                {
                    "id": "chatcmpl-fake",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": "".join(WORDS)}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": len(WORDS), "total_tokens": 5 + len(WORDS)},
                },
            )
            return
        self._stream(model)

    def _stream(self, model: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        delay = {"fake-slow": 1.0, "fake-model": 0.15}.get(model, 0.01)
        words = WORDS * (20000 if model == "fake-huge" else (30 if model == "fake-slow" else 1))
        try:
            for index, word in enumerate(words):
                if model == "fake-drop" and index == 3:
                    # Обрыв посреди ответа: раннер должен сообщить upstream_unreachable.
                    self.connection.close()
                    return
                self.wfile.write(_chunk(word, model))
                self.wfile.flush()
                time.sleep(delay)
            self.wfile.write(_chunk("", model, finish="stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            _count("completed")
        except (BrokenPipeError, ConnectionResetError):
            _count("client_closed")


def main() -> None:
    port = int(os.environ.get("FAKE_OPENAI_PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104 — сервер только во внутренней сети стенда


if __name__ == "__main__":
    main()
