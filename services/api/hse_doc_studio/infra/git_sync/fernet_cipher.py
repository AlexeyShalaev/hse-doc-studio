"""Шифр секретов переехал в `infra.secrets`; модуль оставлен для прежних импортов."""

from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher

__all__ = ["FernetSecretCipher"]
