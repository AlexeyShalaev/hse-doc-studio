from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.backup.destinations import key_hint, normalize_local_path, normalize_prefix, validate_spec
from hse_doc_studio.core.backup.entities import DestinationKind, DestinationSpec, EncryptionMode, Manifest, ManifestPart
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.keys import make_key, open_key
from hse_doc_studio.core.backup.manifest import dump_manifest, is_backup_id, parse_manifest

SHA = "a" * 64


def _manifest(mode: EncryptionMode = EncryptionMode.installation) -> Manifest:
    return Manifest(
        format=1,
        backup_id="20261101T120000Z-ab12cd",
        created_at=datetime(2026, 11, 1, 12, tzinfo=UTC),
        app_version="0.2.0",
        schema_revision="bk_01_backups",
        installation_id="inst",
        encryption_mode=mode,
        salt_hex="00" * 16,
        key_check="c" * 32,
        key_fingerprint="fp",
        parts=(ManifestPart("db.pgdump.enc", 10, SHA, 8, SHA),),
        notes={"files.files": 3},
    )


def test__manifest__roundtrip() -> None:
    manifest = _manifest()
    assert parse_manifest(dump_manifest(manifest)) == manifest


def test__manifest__rejects_garbage_and_unknown_format() -> None:
    with pytest.raises(BackupError):
        parse_manifest(b"not json")
    body = json.loads(dump_manifest(_manifest()))
    body["format"] = 99
    with pytest.raises(BackupError) as unsupported:
        parse_manifest(json.dumps(body).encode())
    assert unsupported.value.code is BackupErrorCode.unsupported
    body["format"] = 1
    body["parts"][0]["name"] = "../evil"
    with pytest.raises(BackupError):
        parse_manifest(json.dumps(body).encode())
    body["parts"][0]["name"] = "ok"
    body["backup_id"] = "../../x"
    with pytest.raises(BackupError):
        parse_manifest(json.dumps(body).encode())


def test__backup_id__format() -> None:
    assert is_backup_id("20261101T120000Z-ab12cd")
    assert not is_backup_id("20261101T120000Z-AB12CD")
    assert not is_backup_id("../20261101T120000Z-ab12cd")


def test__spec__s3_normalizes_and_validates() -> None:
    spec = validate_spec(
        DestinationSpec(
            name="  Main ", kind=DestinationKind.s3, endpoint="http://minio:9000/", bucket="hse-backups", prefix="/a/b/"
        )
    )
    assert (spec.name, spec.endpoint, spec.prefix, spec.region) == ("Main", "http://minio:9000", "a/b", "us-east-1")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"bucket": "UPPER"},
        {"bucket": "ab"},
        {"endpoint": "ftp://x"},
        {"endpoint": "http://user:pass@host"},
        {"prefix": "../etc"},
        {"prefix": "a/../b"},
    ],
)
def test__spec__s3_invalid__rejected(kwargs: dict[str, str]) -> None:
    base = {"name": "n", "kind": DestinationKind.s3, "bucket": "hse-backups"}
    with pytest.raises(BackupError) as caught:
        validate_spec(DestinationSpec(**{**base, **kwargs}))  # type: ignore[arg-type]
    assert caught.value.code is BackupErrorCode.invalid_input


@pytest.mark.parametrize("path", ["", "..", "../x", "a/../../b", "/", ".hidden"])
def test__local_path__escape_or_empty__rejected(path: str) -> None:
    with pytest.raises(BackupError):
        normalize_local_path(path)


def test__local_path__normalized() -> None:
    assert normalize_local_path("/disk1/studio/") == "disk1/studio"
    assert normalize_prefix("") == ""


def test__key_hint__shows_only_tail() -> None:
    assert key_hint("AKIAABCDEFGH1234") == "…1234"
    assert key_hint(None) is None


def test__keys__installation_roundtrip_with_rotated_key() -> None:
    old, new = bytes(range(32)), bytes(range(1, 33))
    salt = bytes(16)
    key = make_key(EncryptionMode.installation, salt, installation_key=old, passphrase=None)
    manifest = Manifest(**{**_manifest().__dict__, "key_check": key.check, "salt_hex": salt.hex()})
    assert open_key(manifest, installation_keys=[new, old], passphrase=None) == key.key
    with pytest.raises(BackupError) as caught:
        open_key(manifest, installation_keys=[new], passphrase=None)
    assert caught.value.code is BackupErrorCode.secrets_unavailable


def test__keys__passphrase_wrong_and_missing() -> None:
    salt = bytes(16)
    key = make_key(EncryptionMode.passphrase, salt, installation_key=None, passphrase="long enough phrase")
    manifest = Manifest(
        **{
            **_manifest().__dict__,
            "key_check": key.check,
            "salt_hex": salt.hex(),
            "encryption_mode": EncryptionMode.passphrase,
        }
    )
    assert open_key(manifest, installation_keys=[], passphrase="long enough phrase") == key.key
    with pytest.raises(BackupError):
        open_key(manifest, installation_keys=[], passphrase="wrong phrase entirely")
    with pytest.raises(BackupError):
        open_key(manifest, installation_keys=[], passphrase=None)
