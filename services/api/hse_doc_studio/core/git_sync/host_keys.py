"""Ключи хостов ssh: имя записи known_hosts, отпечаток SHA256 и разбор строки ключа.

Чистые правила без ввода-вывода. Отпечаток считается так же, как печатает `ssh-keygen -lf`,
поэтому человек сверяет его с тем, что показывает страница хостинга.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re

DEFAULT_SSH_PORT = 22

# Алгоритмы, которые Студия готова принять: ssh-keyscan просят только о них, а строка с другим
# типом (сертификаты, sk-ключи) в хранилище не попадает.
HOST_KEY_TYPES = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521", "ssh-rsa")

_FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def known_host_pattern(host: str, port: int | None) -> str:
    """Имя записи known_hosts: `host` для порта 22, иначе `[host]:port`, как их пишет сам ssh."""
    if port is None or port == DEFAULT_SSH_PORT:
        return host
    return f"[{host}]:{port}"


def normalize_known_port(port: int | None) -> int | None:
    """Порт 22 и отсутствие порта это одна и та же запись."""
    return None if port == DEFAULT_SSH_PORT else port


def key_fingerprint(key_b64: str) -> str:
    """`SHA256:...` по base64-блоку ключа хоста."""
    digest = hashlib.sha256(base64.b64decode(key_b64, validate=True)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def is_fingerprint(text: str) -> bool:
    return bool(_FINGERPRINT.match(text))


def parse_key_fields(key_type: str, key_b64: str) -> tuple[str, str] | None:
    """(тип, base64) или None, если тип неизвестен или блок не base64."""
    if key_type not in HOST_KEY_TYPES:
        return None
    try:
        base64.b64decode(key_b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    return key_type, key_b64
