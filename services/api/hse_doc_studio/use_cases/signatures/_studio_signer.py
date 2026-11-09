"""Подпись ключом из Студии: кто вправе, открепленная над зафиксированным PDF и PAdES дописыванием.

Общая часть одиночной «Подписать в Студии», подписи PAdES и «Подписать комплект» (docs/design/signature-plan.md,
разделы 4, 5 и 7). Пароль ключа живёт только в аргументах вызова: он не пишется в состояние, лог и аудит.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import structlog

from hse_doc_studio.core.entities import Project, SigningIdentity
from hse_doc_studio.core.enums import DetachedOrigin, DetachedVerdict, SigningIdentityKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.repositories import ISigningIdentityRepository
from hse_doc_studio.core.signatures.errors import CmsParseError, GpgError, GpgUnavailableError
from hse_doc_studio.core.signatures.key_policy import ISigningKeyPolicy, require_server_key_storage
from hse_doc_studio.core.signatures.plan import SignMethod, method_of, slot_persona
from hse_doc_studio.core.signatures.ports import IPadesSigner, ISignatureAudit, ISignerScope, ITrustMaterialProvider
from hse_doc_studio.core.signatures.stamps import stamps_digest_matches, stamps_for_doc
from hse_doc_studio.core.signatures.verification import note_plate_mismatch
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    EmbeddedSignature,
    FrozenPdf,
    SignaturesState,
    SignerInfo,
)
from hse_doc_studio.infra.signatures.cades_signer import sign_detached as sign_cades
from hse_doc_studio.infra.signatures.cms_inspector import describe_certificate
from hse_doc_studio.infra.signatures.openpgp import GpgKey, GpgKeyring
from hse_doc_studio.use_cases.signatures._detached_store import store_signature, verify_frozen
from hse_doc_studio.use_cases.signatures._doc_context import FROZEN_DIR, DocContext, safe_name, sha256_file

logger = structlog.get_logger()

X509_KINDS = frozenset({SigningIdentityKind.self_signed, SigningIdentityKind.pkcs12})

_locks: dict[str, asyncio.Lock] = {}


def project_lock(project: Project) -> asyncio.Lock:
    """Подписи одного проекта пишутся по очереди: PAdES дописывает общий файл, состояние одно на проект."""
    return _locks.setdefault(str(project.id), asyncio.Lock())


class SlotNotYoursError(PermissionError):
    def __init__(self, slot_label: str) -> None:
        super().__init__(
            localized_error(
                f"Слот «{slot_label}» подписывает другой участник: своим ключом можно подписать только свои слоты",
                f"Slot “{slot_label}” belongs to another participant: you can sign only your own slots with your key",
            )
        )


class PlateSignerMismatchError(PermissionError):
    def __init__(self, expected: str) -> None:
        super().__init__(
            localized_error(
                f"На плашке указан другой подписант ({expected}): подпишите его ключом или смените подписанта слота",
                f"The plate names another signer ({expected}): sign with their key or change the slot signer",
            )
        )


class KeyPassphraseRequiredError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            localized_error("Ключ защищён паролем: введите пароль", "The key is passphrase-protected: enter it")
        )


def openpgp_signer(key: GpgKey) -> SignerInfo:
    uid = key.uids[0] if key.uids else key.key_id
    owner = uid.split("<")[0].strip() or uid
    pretty = " ".join(key.key_id[i : i + 4] for i in range(0, len(key.key_id), 4))
    return SignerInfo(
        kind="openpgp",
        owner=owner,
        cert_id=pretty,
        valid_from=key.created.isoformat() if key.created else None,
        valid_to=key.expires.isoformat() if key.expires else None,
        signer_id=key.fingerprint,
    )


def x509_signer(blob: bytes) -> SignerInfo:
    info = describe_certificate(blob)
    return SignerInfo(
        kind="x509",
        owner=info.owner,
        cert_id=info.serial,
        valid_from=info.not_before.isoformat(),
        valid_to=info.not_after.isoformat(),
        signer_id=info.fingerprint_sha256,
        level="ukep" if info.qualified_hint else "",
    )


async def signer_for_identity(
    identity: SigningIdentity, keyring: GpgKeyring, identity_repo: ISigningIdentityRepository
) -> SignerInfo:
    """Данные плашки из ключа Студии: владелец, номер сертификата или ключа, срок, отпечаток."""
    if identity.kind is SigningIdentityKind.openpgp and identity.fingerprint:
        key = await asyncio.to_thread(keyring.get_key, identity.fingerprint)
        if key is None:
            raise ValueError(localized_error("Ключ OpenPGP не найден в связке", "OpenPGP key not in the keyring"))
        return openpgp_signer(key)
    cert_pem = await identity_repo.read_cert(identity.id)
    if cert_pem is None:
        raise ValueError(localized_error("У ключа нет сертификата", "The key has no certificate"))
    try:
        return x509_signer(cert_pem)
    except CmsParseError as exc:
        raise ValueError(localized_error("Сертификат ключа не читается", "The key certificate is unreadable")) from exc


def marks_unchanged(ctx: DocContext, state: SignaturesState, frozen: FrozenPdf) -> bool:
    """Видимый слой тот же, что при фиксации (отпечаток прежнего вида тоже принимается)."""
    stamps = stamps_for_doc(state, ctx.doc.id, ctx.project.folder, ctx.lang)
    return stamps_digest_matches(frozen.stamps_digest, stamps, ctx.project.folder)


def signed_file_of(frozen: FrozenPdf) -> str:
    return str(PurePosixPath(FROZEN_DIR) / (PurePosixPath(frozen.path).stem + ".signed.pdf"))


def _prefix_sha256(path: Path, size: int) -> str:
    h = hashlib.sha256()
    left = size
    with path.open("rb") as fh:
        while left > 0:
            chunk = fh.read(min(left, 1 << 20))
            if not chunk:
                break
            h.update(chunk)
            left -= len(chunk)
    return h.hexdigest()


async def current_signed_file(folder: Path, frozen: FrozenPdf) -> Path:
    """Текущий итоговый файл: F со встроенными подписями или, пока их нет, зафиксированный B.

    Отказ, если F не тот, что записан, или не начинается с зафиксированных байтов.
    """
    base = folder / frozen.path
    if not frozen.signed_path:
        return base
    signed = folder / frozen.signed_path
    changed = localized_error(
        "Подписанный PDF изменился вне Студии: зафиксируйте документ заново",
        "The signed PDF changed outside the Studio: freeze the document again",
    )
    if not signed.is_file():
        raise ValueError(changed)
    sha = await asyncio.to_thread(sha256_file, signed)
    prefix = await asyncio.to_thread(_prefix_sha256, signed, frozen.size)
    if sha != frozen.signed_sha256 or prefix != frozen.sha256:
        raise ValueError(changed)
    return signed


@dataclass
class StudioSigner:
    identity_repo: ISigningIdentityRepository
    keyring: GpgKeyring
    dispatcher: IJobDispatcher
    trust_provider: ITrustMaterialProvider
    pades: IPadesSigner
    scope: ISignerScope
    audit: ISignatureAudit
    # Ключи Студии лежат на сервере: при запрете админа они заблокированы, подписать ими нельзя.
    key_policy: ISigningKeyPolicy

    async def require_key_allowed(self) -> None:
        await require_server_key_storage(self.key_policy)

    async def may_sign(
        self, project: Project, state: SignaturesState, slot_id: str, label: str, signer: SignerInfo, *, explicit: bool
    ) -> None:
        """Подписать слот своим ключом можно только за свою персону; ключ должен совпасть с плашкой.

        Локально человек один и персону ему не назначить: явная одиночная подпись слота без указанного на
        плашке подписанта разрешена, а «Подписать комплект» берёт только слоты авторов и слоты с его ключом
        на плашке.
        """
        slot = state.slots.get(slot_id)
        plate = slot.signer if slot is not None else None
        if plate is not None and plate.signer_id and signer.signer_id and plate.signer_id != signer.signer_id:
            raise PlateSignerMismatchError(plate.owner or plate.signer_id)
        if slot_persona(slot_id) in await self.scope.personas(project):
            return
        if explicit and self.scope.single_user() and (plate is None or not plate.signer_id):
            return
        raise SlotNotYoursError(label)

    async def sign_detached(
        self,
        ctx: DocContext,
        state: SignaturesState,
        frozen: FrozenPdf,
        slot_id: str,
        identity: SigningIdentity,
        passphrase: str,
    ) -> tuple[SignaturesState, DetachedSignature]:
        await self.require_key_allowed()
        pdf_path = ctx.project.folder / frozen.path
        sig_bytes = await self._sign_bytes(identity, pdf_path, passphrase)
        verified = await verify_frozen(self.dispatcher, self.trust_provider, ctx, frozen, sig_bytes)
        verified = note_plate_mismatch(state, slot_id, verified)
        new_state, sig = store_signature(ctx, state, slot_id, verified, sig_bytes, DetachedOrigin.studio, frozen)
        await self.audit.record(
            "signature.sign",
            project_id=ctx.project.id,
            details={
                "doc_id": ctx.doc.id,
                "slot_id": slot_id,
                "method": SignMethod.detached.value,
                "format": sig.format.value,
                "verdict": sig.verdict.value,
                "signer_id": sig.signer_id,
            },
        )
        return new_state, sig

    async def sign_pades(
        self,
        ctx: DocContext,
        state: SignaturesState,
        frozen: FrozenPdf,
        slot_id: str,
        identity: SigningIdentity,
        reason: str = "",
    ) -> tuple[SignaturesState, EmbeddedSignature]:
        """Одна ревизия PAdES поверх текущего итогового файла; зафиксированные байты остаются его началом."""
        await self.require_key_allowed()
        if identity.kind not in X509_KINDS:
            raise ValueError(
                localized_error(
                    "Встроенную подпись PAdES делает только ключ с сертификатом X.509 (PKCS#12 или самоподписанный)",
                    "An embedded PAdES signature needs a key with an X.509 certificate (PKCS#12 or self-signed)",
                )
            )
        existing = state.embedded.get(ctx.doc.id, {}).get(slot_id)
        if existing is not None and existing.base_sha256 == frozen.sha256:
            raise ValueError(
                localized_error("Этот слот уже подписан в этой версии PDF", "This slot is already signed in this PDF")
            )
        folder = ctx.project.folder
        current = await current_signed_file(folder, frozen)
        signed_rel = frozen.signed_path or signed_file_of(frozen)
        target = folder / signed_rel
        tmp = target.with_suffix(".pdf.tmp")
        field_name = f"Sig_{safe_name(slot_id)}"
        try:
            async with self.identity_repo.private_key_session(identity.id) as key_dir:
                await self.pades.sign_incremental(current, tmp, field_name, key_dir, reason)
            checks = await self.pades.validate(tmp)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        mine = next((c for c in reversed(checks) if c.field_name == field_name), None)
        others_ok = all(c.intact and c.covers and c.modifications_ok for c in checks if c.field_name != field_name)
        if mine is None or not others_ok or not mine.intact:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                localized_error(
                    "Подпись PAdES не прошла проверку: файл не изменён", "The PAdES signature failed the check"
                )
            )
        tmp.replace(target)
        sha = await asyncio.to_thread(sha256_file, target)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        signature = EmbeddedSignature(
            field_name=field_name,
            base_sha256=frozen.sha256,
            revision_size=mine.revision_size,
            revision_sha256=sha,
            verdict=DetachedVerdict.valid,
            signer=mine.signer,
            signer_id=mine.signer_id,
            added_at=now,
            signed_at=mine.signed_at,
            notes=() if identity.trusted else ("chain_untrusted_root",),
        )
        new_frozen = replace(frozen, signed_path=signed_rel, signed_sha256=sha, signed_size=target.stat().st_size)
        doc_embedded = {**state.embedded.get(ctx.doc.id, {}), slot_id: signature}
        new_state = replace(
            state,
            frozen={**state.frozen, ctx.doc.id: new_frozen},
            embedded={**state.embedded, ctx.doc.id: doc_embedded},
        )
        await self.audit.record(
            "signature.sign",
            project_id=ctx.project.id,
            details={
                "doc_id": ctx.doc.id,
                "slot_id": slot_id,
                "method": SignMethod.pades.value,
                "format": "pades",
                "verdict": signature.verdict.value,
                "signer_id": signature.signer_id,
            },
        )
        return new_state, signature

    async def sign_slot(
        self,
        ctx: DocContext,
        state: SignaturesState,
        frozen: FrozenPdf,
        slot_id: str,
        identity: SigningIdentity,
        passphrase: str,
    ) -> SignaturesState:
        """Подпись слота его способом: открепленная или PAdES. Картинке подписывать нечего."""
        slot = state.slots.get(slot_id)
        method = method_of(slot.sign_mode) if slot is not None else SignMethod.image
        if method is SignMethod.detached:
            return (await self.sign_detached(ctx, state, frozen, slot_id, identity, passphrase))[0]
        if method is SignMethod.pades:
            reason = slot.sign_reason if slot is not None else ""
            return (await self.sign_pades(ctx, state, frozen, slot_id, identity, reason))[0]
        return state

    async def _sign_bytes(self, identity: SigningIdentity, pdf_path: Path, passphrase: str) -> bytes:
        if identity.kind is SigningIdentityKind.openpgp:
            return await asyncio.to_thread(self._sign_openpgp, identity, pdf_path, passphrase)
        if identity.kind in X509_KINDS:
            async with self.identity_repo.private_key_session(identity.id) as key_dir:
                return await asyncio.to_thread(_sign_cades_bytes, pdf_path, key_dir)
        raise ValueError(
            localized_error(
                "Этим ключом нельзя подписать в Студии. Подпишите файл в КриптоАРМ/КриптоПро и загрузите подпись",
                "This key cannot sign inside the Studio. Sign the file in CryptoARM/CryptoPro and upload the signature",
            )
        )

    def _sign_openpgp(self, identity: SigningIdentity, pdf_path: Path, passphrase: str) -> bytes:
        if not identity.fingerprint:
            raise ValueError(localized_error("У ключа нет отпечатка", "The key has no fingerprint"))
        if identity.protected and not passphrase:
            raise KeyPassphraseRequiredError
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sig.asc"
            try:
                self.keyring.sign_detached(pdf_path, identity.fingerprint, out, passphrase=passphrase)
            except GpgUnavailableError as exc:
                raise ValueError(localized_error("В системе нет gpg", "gpg is not installed")) from exc
            except GpgError as exc:
                raise ValueError(
                    localized_error(f"gpg отказал в подписи: {exc}", f"gpg refused to sign: {exc}")
                ) from exc
            return out.read_bytes()


def _sign_cades_bytes(pdf_path: Path, key_dir: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sig.p7s"
        try:
            sign_cades(pdf_path, out, key_dir)
        except ValueError as exc:
            raise ValueError(localized_error(f"Не удалось подписать: {exc}", f"Signing failed: {exc}")) from exc
        return out.read_bytes()


def drop_signed_file(folder: Path, frozen: FrozenPdf | None) -> None:
    if frozen is not None and frozen.signed_path:
        with contextlib.suppress(OSError):
            (folder / frozen.signed_path).unlink()
