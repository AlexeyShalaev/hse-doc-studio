from __future__ import annotations


class ObjectStoreError(Exception):
    """Хранилище отказало: недоступно, нет прав или ответило ошибкой."""


class ObjectNotFoundError(ObjectStoreError):
    """Объекта с таким ключом нет."""


class InvalidObjectKeyError(ObjectStoreError, ValueError):
    """Ключ пустой, абсолютный, содержит `..` или скрытый сегмент."""


class ChecksumMismatchError(ObjectStoreError):
    """sha256 данных не совпал с заявленным; в хранилище ничего не записано."""


class ObjectTooLargeError(ObjectStoreError):
    """Объект больше разрешённого предела."""
