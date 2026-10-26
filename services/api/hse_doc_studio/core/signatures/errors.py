"""Ошибки работы с открепленными подписями: общие для infra и use_cases."""

from __future__ import annotations


class GpgUnavailableError(RuntimeError):
    """The gpg binary is not installed."""


class GpgError(ValueError):
    """gpg refused the operation (bad key, wrong passphrase, ...)."""


class CmsParseError(ValueError):
    """The blob is not a CMS SignedData structure."""


class UnknownSignatureFormatError(ValueError):
    """The file is neither an OpenPGP nor a CMS signature."""
