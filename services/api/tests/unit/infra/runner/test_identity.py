from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.jobs.wire import RunnerRegisterResponse
from hse_doc_studio.infra.runner.identity import IDENTITY_FILE, RunnerIdentityStore

_REGISTERED = RunnerRegisterResponse(
    runner_id="r1", runner_token="hsrn_secret", lease_s=45, heartbeat_s=10, max_poll_wait_s=25
)


def test_save_then_load__same_api__returns_identity(tmp_path: Path) -> None:
    store = RunnerIdentityStore(tmp_path)
    store.save("http://api", _REGISTERED)

    identity = store.load("http://api")

    assert identity is not None
    assert (identity.runner_id, identity.runner_token) == ("r1", "hsrn_secret")


def test_load__other_api__is_not_registered(tmp_path: Path) -> None:
    store = RunnerIdentityStore(tmp_path)
    store.save("http://api", _REGISTERED)

    assert store.load("http://other") is None


def test_load__missing_or_broken_file__is_not_registered(tmp_path: Path) -> None:
    store = RunnerIdentityStore(tmp_path)
    assert store.load("http://api") is None

    (tmp_path / IDENTITY_FILE).write_text("{not json", encoding="utf-8")
    assert store.load("http://api") is None


def test_forget__removes_the_file(tmp_path: Path) -> None:
    store = RunnerIdentityStore(tmp_path)
    store.save("http://api", _REGISTERED)

    store.forget()

    assert store.load("http://api") is None
