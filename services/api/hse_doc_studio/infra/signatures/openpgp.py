"""OpenPGP detached signatures through the `gpg` binary.

One private keyring lives in `home` (data_dir/gnupg). It holds the user's own
secret keys and every public key somebody uploaded to check a signature. The
binary is only ever driven non-interactively (`--batch`, loopback pinentry,
passphrase on stdin), and the passphrase never reaches argv.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import structlog

from hse_doc_studio.core.signatures.errors import GpgError, GpgUnavailableError

logger = structlog.get_logger()

VerifyStatus = Literal["good", "bad", "no_pubkey", "expired_key", "expired_signature", "revoked_key", "error"]

_TIMEOUT = 60.0
_MAX_HOME_BYTES = 80


@dataclass(frozen=True)
class GpgKey:
    fingerprint: str
    key_id: str
    uids: list[str]
    has_secret: bool
    algo: str
    created: datetime | None
    expires: datetime | None


@dataclass(frozen=True)
class GpgVerification:
    status: VerifyStatus
    fingerprint: str | None = None
    key_id: str | None = None
    signer: str = ""
    signed_at: datetime | None = None
    note: str = ""
    # Primary-key fingerprint when the signature came from a subkey.
    primary_fingerprint: str | None = None
    extra: list[str] = field(default_factory=list)


def _ts(raw: str) -> datetime | None:
    if not raw or raw == "0":
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (ValueError, OverflowError):
        return None


class GpgKeyring:
    def __init__(self, home: Path, binary: str | None = None) -> None:
        self._home = home
        self._binary = binary or shutil.which("gpg")
        self._cmd_home: Path | None = None

    @property
    def available(self) -> bool:
        return self._binary is not None

    def version(self) -> str | None:
        if not self._binary:
            return None
        out = subprocess.run(  # noqa: S603
            [self._binary, "--version"], capture_output=True, text=True, timeout=_TIMEOUT, check=False
        )
        first = out.stdout.splitlines()[0] if out.stdout else ""
        return first.removeprefix("gpg (GnuPG) ").strip() or None

    # ── low level ────────────────────────────────────────────────────────────

    def _run(
        self,
        args: list[str],
        *,
        stdin: bytes | None = None,
        passphrase: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        if not self._binary:
            raise GpgUnavailableError("gpg is not installed")
        self._home.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self._home.chmod(0o700)
        cmd = [self._binary, "--homedir", str(self._effective_home()), "--batch", "--no-tty", "--yes"]
        data = stdin
        if passphrase is not None:
            cmd += ["--pinentry-mode", "loopback", "--passphrase-fd", "0"]
            data = passphrase.encode() + b"\n" + (stdin or b"")
        proc = subprocess.run(  # noqa: S603
            [*cmd, *args], input=data, capture_output=True, timeout=_TIMEOUT, check=False
        )
        if check and proc.returncode != 0:
            raise GpgError(_clean_stderr(proc.stderr))
        return proc

    def _effective_home(self) -> Path:
        """The keyring path handed to gpg.

        gpg-agent keeps a unix socket inside the home directory and the OS limits
        socket paths to ~104 bytes, so a deep data folder (a developer's home on
        macOS, a synced drive) goes through a short symlink instead.
        """
        if len(str(self._home).encode()) <= _MAX_HOME_BYTES:
            return self._home
        if self._cmd_home is None:
            digest = hashlib.sha1(str(self._home).encode(), usedforsecurity=False).hexdigest()[:12]
            link = Path(tempfile.gettempdir()) / f"hds-gnupg-{digest}"
            if link.is_symlink() and link.resolve() != self._home.resolve():
                link.unlink()
            if not link.exists():
                self._home.mkdir(parents=True, exist_ok=True)
                link.symlink_to(self._home, target_is_directory=True)
            self._cmd_home = link
        return self._cmd_home

    def stop_agent(self) -> None:
        gpgconf = shutil.which("gpgconf")
        if gpgconf and self._home.exists():
            subprocess.run(  # noqa: S603
                [gpgconf, "--homedir", str(self._effective_home()), "--kill", "gpg-agent"],
                capture_output=True,
                timeout=_TIMEOUT,
                check=False,
            )

    # ── keys ─────────────────────────────────────────────────────────────────

    def list_keys(self, *, fingerprint: str | None = None) -> list[GpgKey]:
        if not self._binary or not self._home.exists():
            return []
        extra = [fingerprint] if fingerprint else []
        pub = self._run(["--with-colons", "--fixed-list-mode", "--list-keys", *extra], check=False)
        sec = self._run(["--with-colons", "--fixed-list-mode", "--list-secret-keys", *extra], check=False)
        secret = _secret_fingerprints(sec.stdout)
        return [replace(k, has_secret=k.fingerprint in secret) for k in _keys_from_colons(pub.stdout)]

    def get_key(self, fingerprint: str) -> GpgKey | None:
        keys = self.list_keys(fingerprint=fingerprint)
        return keys[0] if keys else None

    def generate(self, name: str, email: str, passphrase: str = "") -> GpgKey:
        """New ed25519 signing key, no expiry. Empty passphrase = unprotected key."""
        uid = f"{name} <{email}>" if email else name
        self._run(["--quick-generate-key", uid, "ed25519", "sign", "never"], passphrase=passphrase)
        keys = [k for k in self.list_keys() if k.has_secret and uid in k.uids]
        if not keys:
            raise GpgError("key was generated but cannot be found in the keyring")
        return keys[-1]

    def import_key(self, data: bytes, passphrase: str | None = None) -> list[GpgKey]:
        """Import an armored/binary public or secret key; returns the keys it contained."""
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "key.asc"
            key_file.write_bytes(data)
            proc = self._run(["--status-fd", "1", "--import", str(key_file)], passphrase=passphrase, check=False)
        fprs = {
            parts[3]
            for parts in (ln.split() for ln in proc.stdout.decode("utf-8", "replace").splitlines())
            if len(parts) >= 4 and parts[1] == "IMPORT_OK"
        }
        if not fprs:
            raise GpgError(_clean_stderr(proc.stderr) or "no OpenPGP key found in the file")
        return [k for k in self.list_keys() if k.fingerprint in fprs]

    def looks_like_public_key(self, blob: bytes) -> bool:
        return looks_like_openpgp_public_key(blob)

    def import_public_key(self, blob: bytes) -> None:
        self.import_key(blob)

    def export_public(self, fingerprint: str) -> bytes:
        return self._run(["--armor", "--export", fingerprint]).stdout

    def delete(self, fingerprint: str) -> None:
        self._run(["--delete-secret-and-public-key", "--pinentry-mode", "loopback", fingerprint], check=False)
        self._run(["--delete-keys", fingerprint], check=False)

    def is_protected(self, fingerprint: str) -> bool:
        """True when signing with an empty passphrase fails (key needs a passphrase)."""
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "probe"
            probe.write_bytes(b"probe")
            try:
                self.sign_detached(probe, fingerprint, Path(tmp) / "probe.asc", passphrase="")
            except GpgError:
                return True
        return False

    # ── signatures ───────────────────────────────────────────────────────────

    def sign_detached(self, data_path: Path, fingerprint: str, out_path: Path, passphrase: str = "") -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            ["--armor", "--local-user", f"{fingerprint}!", "--output", str(out_path), "--detach-sign", str(data_path)],
            passphrase=passphrase,
        )

    def verify_detached(self, sig_path: Path, data_path: Path) -> GpgVerification:
        proc = self._run(["--status-fd", "1", "--verify", str(sig_path), str(data_path)], check=False)
        return _parse_verify(proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace"))


def looks_like_openpgp_signature(blob: bytes) -> bool:
    if blob.lstrip()[:36].startswith(b"-----BEGIN PGP SIGNATURE-----"):
        return True
    # Binary packet: new- or old-format header with the signature tag (2).
    if not blob:
        return False
    first = blob[0]
    if first & 0x80 == 0:
        return False
    tag = first & 0x3F if first & 0x40 else (first >> 2) & 0x0F
    return tag == 2


def looks_like_openpgp_public_key(blob: bytes) -> bool:
    return blob.lstrip()[:40].startswith(b"-----BEGIN PGP PUBLIC KEY BLOCK-----")


def looks_like_openpgp_key(blob: bytes) -> bool:
    head = blob.lstrip()[:40]
    return head.startswith((b"-----BEGIN PGP PUBLIC KEY BLOCK-----", b"-----BEGIN PGP PRIVATE KEY BLOCK-----"))


# ── parsing ──────────────────────────────────────────────────────────────────


def _clean_stderr(raw: bytes) -> str:
    lines = [ln for ln in raw.decode("utf-8", "replace").splitlines() if ln.strip()]
    return "; ".join(ln.removeprefix("gpg: ") for ln in lines[-3:])


def _secret_fingerprints(raw: bytes) -> set[str]:
    """Primary-key fingerprints from `--list-secret-keys --with-colons`."""
    result: set[str] = set()
    expect = False
    for line in raw.decode("utf-8", "replace").splitlines():
        cols = line.split(":")
        if cols[0] == "sec":
            expect = True
        elif cols[0] == "fpr" and expect and len(cols) > 9:
            result.add(cols[9])
            expect = False
        elif cols[0] == "ssb":
            expect = False
    return result


_ALGOS = {"1": "rsa", "17": "dsa", "18": "ecdh", "19": "ecdsa", "22": "ed25519", "16": "elgamal"}


def _keys_from_colons(raw: bytes) -> list[GpgKey]:  # noqa: C901
    keys: list[GpgKey] = []
    cur: dict[str, object] | None = None
    expect_fpr = False

    def flush() -> None:
        if cur:
            keys.append(
                GpgKey(
                    fingerprint=str(cur["fpr"]),
                    key_id=str(cur["fpr"])[-16:],
                    uids=list(cur["uids"]),  # type: ignore[call-overload]
                    has_secret=False,
                    algo=str(cur["algo"]),
                    created=cur["created"],  # type: ignore[arg-type]
                    expires=cur["expires"],  # type: ignore[arg-type]
                )
            )

    for line in raw.decode("utf-8", "replace").splitlines():
        cols = line.split(":")
        rec = cols[0]
        if rec == "pub":
            flush()
            cur = {
                "fpr": "",
                "uids": [],
                "algo": _ALGOS.get(cols[3], cols[3]),
                "created": _ts(cols[5]),
                "expires": _ts(cols[6]),
            }
            expect_fpr = True
        elif rec == "fpr" and cur is not None and expect_fpr:
            cur["fpr"] = cols[9]
            expect_fpr = False
        elif rec == "uid" and cur is not None and cols[1] not in {"r", "e"}:
            cur["uids"].append(_unescape(cols[9]))  # type: ignore[attr-defined]
        elif rec == "sub":
            expect_fpr = False
    flush()
    return keys


def _unescape(value: str) -> str:
    return value.replace("\\x3a", ":").replace("\\x5c", "\\")


_STATUS_MAP: dict[str, VerifyStatus] = {
    "GOODSIG": "good",
    "BADSIG": "bad",
    "EXPKEYSIG": "expired_key",
    "EXPSIG": "expired_signature",
    "REVKEYSIG": "revoked_key",
}


def _parse_verify(status_out: str, stderr: str) -> GpgVerification:  # noqa: C901
    status: VerifyStatus | None = None
    key_id: str | None = None
    signer = ""
    fpr: str | None = None
    primary: str | None = None
    signed_at: datetime | None = None
    for line in status_out.splitlines():
        if not line.startswith("[GNUPG:] "):
            continue
        parts = line[9:].split(" ")
        tag = parts[0]
        if tag in _STATUS_MAP:
            status = _STATUS_MAP[tag]
            key_id = parts[1]
            signer = " ".join(parts[2:])
        elif tag == "VALIDSIG":
            fpr = parts[1]
            signed_at = _ts(parts[3]) if len(parts) > 3 else None
            primary = parts[-1] if len(parts[-1]) >= 40 else None
        elif tag == "NO_PUBKEY":
            status = "no_pubkey"
            key_id = parts[1]
        elif tag == "ERRSIG" and status is None:
            status = "error"
            key_id = parts[1]
    if status is None:
        return GpgVerification(status="error", note=_clean_stderr(stderr.encode()))
    return GpgVerification(
        status=status,
        fingerprint=fpr,
        key_id=key_id,
        signer=signer,
        signed_at=signed_at,
        primary_fingerprint=primary,
    )
