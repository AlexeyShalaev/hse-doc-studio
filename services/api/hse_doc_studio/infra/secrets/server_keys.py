"""Ключ шифрования серверного режима: только из окружения, файла в данных нет.

Файл ключа рядом с базой лежал бы там же, где и украденный дамп. Потеря ключа необратима: сохранённые
секреты (токены git, пароли SMTP, ключи ИИ) прочитать нельзя, их вводят заново.
"""

from __future__ import annotations

from hse_doc_studio.api.config import Settings
from hse_doc_studio.infra.secrets.key_store import KeyFileStore


class SecretsKeyMissingError(RuntimeError):
    """В server не задан или негоден ключ шифрования секретов."""


def server_key_store(cfg: Settings) -> KeyFileStore:
    secrets_cfg = cfg.secrets
    key = secrets_cfg.key.get_secret_value().strip() if secrets_cfg.key else ""
    if not key and secrets_cfg.key_file is None:
        msg = (
            "В режиме server нужен ключ шифрования секретов: задайте HSE_STUDIO__SECRETS__KEY или "
            "HSE_STUDIO__SECRETS__KEY_FILE (Fernet-ключ, `python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'`). Сохраните его: без ключа секреты не прочитать."
        )
        raise SecretsKeyMissingError(msg)
    store = KeyFileStore(
        cfg.data_dir.expanduser() / "secrets" / "master.keys.json",
        env_key=key or None,
        env_key_file=secrets_cfg.key_file,
        retired_keys=None if secrets_cfg.retired_keys is None else secrets_cfg.retired_keys.get_secret_value(),
    )
    if not store.status().available:
        msg = (
            "Ключ шифрования секретов (HSE_STUDIO__SECRETS__KEY, KEY_FILE или RETIRED_KEYS) негоден: "
            "нужен Fernet-ключ (urlsafe base64 от 32 байт)."
        )
        raise SecretsKeyMissingError(msg)
    return store


def secrets_key_problem(cfg: Settings) -> str | None:
    """Причина для проверки готовности: None, когда ключ задан и годен."""
    try:
        server_key_store(cfg)
    except SecretsKeyMissingError as exc:
        return str(exc)
    return None


__all__ = ["SecretsKeyMissingError", "secrets_key_problem", "server_key_store"]
