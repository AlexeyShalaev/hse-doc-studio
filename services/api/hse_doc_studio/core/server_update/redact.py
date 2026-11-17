"""Очистка текстов исполнителя перед показом в админке: без секретов, адресов и путей хоста.

Тексты событий и ошибок приходят от апдейтера (вывод docker, Job, Kubernetes API) и могут содержать токены, строки
подключения, внутренние адреса и пути файловой системы. В журнале запуска лежит исходный текст, наружу уходит очищенный:
владелец копирует «Подробности для поддержки» в чат или тикет и не должен выдавать лишнего.
"""

from __future__ import annotations

import re

_MARK = "[redacted]"
_PATH = "[path]"
_ADDR = "[address]"

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer xxx, Bearer xxx
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*)?bearer\s+[\w.~+/=-]+"), f"Bearer {_MARK}"),
    # token=..., password: ..., secret=..., api_key=..., dsn=...
    (
        re.compile(
            r"(?i)\b([\w.-]*(?:token|secret|passw(?:or)?d|passwd|api[_-]?key|dsn|credentials?))(\s*[=:]\s*)(\S+)"
        ),
        rf"\1\2{_MARK}",
    ),
    # scheme://user:pass@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@]+@"), rf"\1{_MARK}@"),
    # внутренние имена служб кластера
    (re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.svc(?:\.cluster\.local)?(?::\d+)?\b"), _ADDR),
    # IPv4 с необязательным портом
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), _ADDR),
    # абсолютные пути; https://host/a/b и образы registry/repo не задеваются (перед слэшем буква или двоеточие)
    (re.compile(r"(?<![\w./:@-])/(?:[\w.@+-]+/)*[\w.@+-]+"), _PATH),
)


def redact(text: str) -> str:
    """Текст без секретов, внутренних адресов и абсолютных путей."""
    out = text
    for pattern, repl in _RULES:
        out = pattern.sub(repl, out)
    return out
