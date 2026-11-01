"""Почтовик по настройкам установки: подхватывает правку админа без перезапуска, окружение побеждает."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.identity.smtp_settings import SmtpEnv, SmtpParams
from hse_doc_studio.infra.identity.configured_mailer import ConfiguredMailSender
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService

from tests.fakes.identity import InMemoryInstanceSettingsRepository


def _service(
    tmp_path: Path, env: SmtpEnv | None = None
) -> tuple[SmtpSettingsService, InMemoryInstanceSettingsRepository]:
    repo = InMemoryInstanceSettingsRepository()
    return SmtpSettingsService(repo, FernetSecretCipher(KeyFileStore(tmp_path / "k")), env), repo


async def test__refresh__without_host_mail_is_off_and_send_fails(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    sender = ConfiguredMailSender(service)

    await sender.refresh()

    assert sender.enabled is False
    with pytest.raises(RuntimeError):
        await sender.send("a@example.org", "s", "b")


async def test__refresh__picks_up_the_admin_host_and_decrypts_the_password(tmp_path: Path) -> None:
    service, repo = _service(tmp_path)
    sender = ConfiguredMailSender(service)
    await sender.refresh()

    await repo.set("smtp.host", "smtp.example.org", source="admin")
    await repo.set_secret("smtp.password", service.seal("pw"), source="admin")
    await sender.refresh()
    params = await service.params()

    assert sender.enabled is True
    assert params is not None
    assert (params.host, params.password) == ("smtp.example.org", "pw")


async def test__params__env_wins_over_stored_values(tmp_path: Path) -> None:
    env = SmtpEnv(SmtpParams(host="smtp.env.example"))
    service, repo = _service(tmp_path, env)
    await repo.set("smtp.host", "smtp.admin.example", source="admin")

    params = await service.params()

    assert params is not None
    assert params.host == "smtp.env.example"


async def test__params__password_from_another_record_does_not_open(tmp_path: Path) -> None:
    service, repo = _service(tmp_path)
    await repo.set("smtp.host", "smtp.example.org", source="admin")
    cipher = FernetSecretCipher(KeyFileStore(tmp_path / "k"))
    from hse_doc_studio.core.git_sync.secret import Secret

    await repo.set_secret("smtp.password", cipher.encrypt(Secret("pw"), aad="other/column/id"), source="admin")

    params = await service.params()

    assert params is not None
    assert params.password is None
