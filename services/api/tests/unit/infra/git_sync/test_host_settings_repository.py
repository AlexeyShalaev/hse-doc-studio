from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_settings import GitHostSettings
from hse_doc_studio.core.git_sync.providers import ApiDetection, GitProvider
from hse_doc_studio.infra.git_sync.host_settings_repository import JsonGitHostSettingsRepository

from tests.fixtures.tls import make_ca_signed, make_self_signed

_posix_only = pytest.mark.skipif(os.name != "posix", reason="file modes are posix-only")


def _unreadable(monkeypatch: pytest.MonkeyPatch, target: Path, error: OSError | None = None) -> None:
    """Чтение этого файла падает, как при блокировке клиентом синхронизации; остальное работает."""
    original = Path.read_bytes
    failure = error or PermissionError("locked")

    def read_bytes(self: Path) -> bytes:
        if self == target:
            raise failure
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)


@pytest.fixture
def repo(tmp_path: Path) -> JsonGitHostSettingsRepository:
    return JsonGitHostSettingsRepository(tmp_path / "data")


async def test__get__fresh_install__is_none_and_list_is_empty(repo: JsonGitHostSettingsRepository) -> None:
    assert await repo.get("git.hse.local", None) is None
    assert await repo.list() == []


async def test__save__all_fields__survive_a_new_repository_instance(tmp_path: Path) -> None:
    settings = GitHostSettings(
        host="git.hse.local",
        port=8443,
        provider_override=GitProvider.gitlab,
        ca_pem="CA",
        pinned_fingerprint="SHA256:abc",
        pinned_pem="PIN",
        detected=ApiDetection(GitProvider.gitlab, "17.3.1", "https://git.hse.local:8443/api/v4"),
    )
    await JsonGitHostSettingsRepository(tmp_path).save(settings)

    assert await JsonGitHostSettingsRepository(tmp_path).get("git.hse.local", 8443) == settings


async def test__get__port_is_part_of_the_key(repo: JsonGitHostSettingsRepository) -> None:
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitlab))
    await repo.save(GitHostSettings("git.hse.local", 8443, provider_override=GitProvider.gitea))

    assert await repo.get("git.hse.local", None) is not None
    assert await repo.get("git.hse.local", None) != await repo.get("git.hse.local", 8443)
    assert len(await repo.list()) == 2


async def test__save__replaces_the_record_of_the_same_server(repo: JsonGitHostSettingsRepository) -> None:
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitlab))
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitea))

    assert [item.provider_override for item in await repo.list()] == [GitProvider.gitea]


async def test__save__empty_record__removes_the_server(repo: JsonGitHostSettingsRepository) -> None:
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitlab))

    await repo.save(GitHostSettings("git.hse.local", None))

    assert await repo.list() == []


async def test__save__detection_cache_alone__keeps_the_record(repo: JsonGitHostSettingsRepository) -> None:
    await repo.save(GitHostSettings("git.hse.local", None, detected=ApiDetection(GitProvider.gitea, "1.22.3")))

    assert len(await repo.list()) == 1


async def test__trust_file__no_trust__is_none_and_nothing_is_written(
    repo: JsonGitHostSettingsRepository, tmp_path: Path
) -> None:
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitlab))

    assert repo.trust_file("git.hse.local", None) is None
    assert not (tmp_path / "data" / "git" / "trust").exists()


async def test__trust_file__ca_and_pin__are_joined_into_one_pem_file(
    repo: JsonGitHostSettingsRepository, tmp_path: Path
) -> None:
    ca, leaf = make_ca_signed(tmp_path / "a"), make_self_signed(tmp_path / "b")
    assert ca.ca_pem is not None
    await repo.save(GitHostSettings("git.hse.local", None, ca_pem=ca.ca_pem, pinned_pem=leaf.cert_pem))

    path = repo.trust_file("git.hse.local", None)

    assert path is not None
    assert path.read_text(encoding="ascii") == ca.ca_pem + leaf.cert_pem


async def test__trust_file__is_rebuilt_when_the_record_changes_or_the_file_is_lost(
    repo: JsonGitHostSettingsRepository, tmp_path: Path
) -> None:
    first = make_self_signed(tmp_path / "a", "first")
    second = make_self_signed(tmp_path / "b", "second")
    await repo.save(GitHostSettings("git.hse.local", None, ca_pem=first.cert_pem))
    path = repo.trust_file("git.hse.local", None)
    assert path is not None
    path.unlink()

    assert repo.trust_file("git.hse.local", None) == path
    assert path.read_text(encoding="ascii") == first.cert_pem
    await repo.save(GitHostSettings("git.hse.local", None, ca_pem=second.cert_pem))
    assert repo.trust_file("git.hse.local", None) == path
    assert path.read_text(encoding="ascii") == second.cert_pem


@_posix_only
async def test__files__are_private_to_the_user(repo: JsonGitHostSettingsRepository, tmp_path: Path) -> None:
    material = make_self_signed(tmp_path / "a")
    await repo.save(GitHostSettings("git.hse.local", None, ca_pem=material.cert_pem))
    trust = repo.trust_file("git.hse.local", None)

    assert trust is not None
    settings_file = tmp_path / "data" / "git" / "host_settings.json"
    assert stat.S_IMODE(settings_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(trust.stat().st_mode) == 0o600
    assert stat.S_IMODE(trust.parent.stat().st_mode) == 0o700


async def test__list__damaged_file__is_empty_and_set_aside_on_the_next_write(
    repo: JsonGitHostSettingsRepository, tmp_path: Path
) -> None:
    path = tmp_path / "data" / "git" / "host_settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    assert await repo.list() == []
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitlab))

    assert len(await repo.list()) == 1
    assert list(path.parent.glob("host_settings.json.corrupt-*"))


async def test__save__read_error__fails_and_keeps_the_saved_settings(
    repo: JsonGitHostSettingsRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data" / "git" / "host_settings.json"
    await repo.save(GitHostSettings("git.hse.local", None, ca_pem="CA"))
    before = path.read_bytes()

    with monkeypatch.context() as patch:
        _unreadable(patch, path)
        assert await repo.list() == []
        with pytest.raises(GitSyncError) as raised:
            await repo.save(GitHostSettings("other.local", None, provider_override=GitProvider.gitea))

    assert raised.value.code is GitErrorCode.secrets_unavailable
    assert list(path.parent.glob("host_settings.json.corrupt-*")) == []
    assert path.read_bytes() == before
    assert [item.host for item in await repo.list()] == ["git.hse.local"]


async def test__list__malformed_record__is_skipped_and_others_are_kept(
    repo: JsonGitHostSettingsRepository, tmp_path: Path
) -> None:
    await repo.save(GitHostSettings("git.hse.local", None, provider_override=GitProvider.gitlab))
    path = tmp_path / "data" / "git" / "host_settings.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"hosts": [', '"hosts": [{"port": 1, "provider_override": "nope"}, '),
        encoding="utf-8",
    )

    assert [item.host for item in await repo.list()] == ["git.hse.local"]


async def test__get__default_https_port_is_the_same_server_as_no_port(repo: JsonGitHostSettingsRepository) -> None:
    await repo.save(GitHostSettings("git.hse.local", 443, provider_override=GitProvider.gitlab))

    assert await repo.get("git.hse.local", None) is not None
    assert await repo.get("git.hse.local", 443) == await repo.get("git.hse.local", None)
