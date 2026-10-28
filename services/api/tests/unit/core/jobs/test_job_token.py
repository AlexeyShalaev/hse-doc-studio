from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.runners import JOB_TOKEN_KEY_PURPOSE, JobTokenSigner
from hse_doc_studio.infra.secrets.key_ring import ENV_KEY_ID, KeyRing

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _ring(*keys: bytes) -> KeyRing:
    return KeyRing(ENV_KEY_ID, {ENV_KEY_ID: keys[0], **{f"old{i}": k for i, k in enumerate(keys[1:])}})


def _signer(ring: KeyRing) -> JobTokenSigner:
    return JobTokenSigner(ring.derive_all(JOB_TOKEN_KEY_PURPOSE))


def _invalid(signer: JobTokenSigner, token: str, **kwargs: str) -> None:
    with pytest.raises(RunnerAuthError) as err:
        signer.verify(token, NOW, **kwargs)
    assert err.value.code is RunnerErrorCode.job_token_invalid


def test__verify__fresh_token__returns_claims() -> None:
    signer = _signer(_ring(Fernet.generate_key()))
    token = signer.sign("job-1", "runner-1", NOW + timedelta(minutes=5))

    claims = signer.verify(token, NOW, job_id="job-1", runner_id="runner-1")

    assert (claims.job_id, claims.runner_id) == ("job-1", "runner-1")
    assert claims.expires_at == NOW + timedelta(minutes=5)


def test__verify__expired_token__rejected() -> None:
    signer = _signer(_ring(Fernet.generate_key()))
    token = signer.sign("job-1", "runner-1", NOW - timedelta(seconds=1))

    _invalid(signer, token)


def test__verify__token_of_another_job_or_runner__rejected() -> None:
    signer = _signer(_ring(Fernet.generate_key()))
    token = signer.sign("job-1", "runner-1", NOW + timedelta(minutes=5))

    _invalid(signer, token, job_id="job-2")
    _invalid(signer, token, runner_id="runner-2")


def test__verify__tampered_payload__rejected() -> None:
    signer = _signer(_ring(Fernet.generate_key()))
    token = signer.sign("job-1", "runner-1", NOW + timedelta(minutes=5))
    version, _payload, mac = token.split(".")
    forged = base64.urlsafe_b64encode(b'{"e":4102444800,"j":"job-1","r":"runner-9"}').rstrip(b"=").decode()

    _invalid(signer, f"{version}.{forged}.{mac}")


@pytest.mark.parametrize("expiry", ["99999999999999999999", "1e400", "Infinity", "-Infinity", "NaN"])
def test__verify__forged_expiry_out_of_range__rejected(expiry: str) -> None:
    signer = _signer(_ring(Fernet.generate_key()))
    version, _payload, mac = signer.sign("job-1", "runner-1", NOW + timedelta(minutes=5)).split(".")
    body = f'{{"e":{expiry},"j":"job-1","r":"runner-1"}}'.encode()
    forged = base64.urlsafe_b64encode(body).rstrip(b"=").decode()

    _invalid(signer, f"{version}.{forged}.{mac}")


def test__verify__signed_with_foreign_key__rejected() -> None:
    mine = _signer(_ring(Fernet.generate_key()))
    foreign = _signer(_ring(Fernet.generate_key()))

    _invalid(mine, foreign.sign("job-1", "runner-1", NOW + timedelta(minutes=5)))


@pytest.mark.parametrize("garbage", ["", "x", "v1..", "v1.a.b", "v2.a.b", "a.b.c.d", "v1.!!.!!"])
def test__verify__garbage__rejected(garbage: str) -> None:
    _invalid(_signer(_ring(Fernet.generate_key())), garbage)


def test__verify__after_key_rotation__old_tokens_survive_while_old_key_is_retired_not_dropped() -> None:
    old_key, new_key = Fernet.generate_key(), Fernet.generate_key()
    token = _signer(_ring(old_key)).sign("job-1", "runner-1", NOW + timedelta(minutes=5))

    rotated = _signer(_ring(new_key, old_key))
    dropped = _signer(_ring(new_key))

    assert rotated.verify(token, NOW).job_id == "job-1"
    _invalid(dropped, token)
    # Новые токены подписывает уже новый ключ.
    assert dropped.verify(rotated.sign("job-2", "runner-1", NOW + timedelta(minutes=5)), NOW).job_id == "job-2"


def test__derive__purposes_give_independent_keys() -> None:
    ring = _ring(Fernet.generate_key())

    assert ring.derive("job-token") != ring.derive("setup-token")
    assert ring.derive("job-token") != ring.primary
