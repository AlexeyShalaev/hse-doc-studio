"""`/api/admin/runner-install/ssh`: отпечаток до входа, SSRF, одноразовые данные, сохранение, повтор, аудит."""

# ruff: noqa: F811 — фикстура `stack` общая с test_admin_ops_api и передаётся параметром
from __future__ import annotations

import asyncio
import shlex
from datetime import UTC, datetime
from typing import Any

from hse_doc_studio.core.egress import EgressBlockReason
from hse_doc_studio.core.runner_install import SshResult
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter

from tests.fakes.ssh import HOST_KEY, LINUX_RECON, find_call
from tests.integration.api.admin.test_admin_ops_api import _Stack, stack  # noqa: F401

BASE = "/api/admin/runner-install/ssh"
PASSWORD = "right-password"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nSECRETKEYBODY\n-----END OPENSSH PRIVATE KEY-----"


def _probe_body(**extra: Any) -> dict[str, Any]:
    return {
        "host": "srv.example.org",
        "port": 22,
        "username": "deploy",
        "auth_kind": "password",
        "password": PASSWORD,
        **extra,
    }


async def _admin(stack: _Stack) -> dict[str, str]:
    return await stack.users.add("boss", admin=True)


async def _probe(stack: _Stack, boss: dict[str, str], **extra: Any) -> dict[str, Any]:
    response = await stack.client.post(f"{BASE}/probe", json=_probe_body(**extra), headers=boss)
    assert response.status_code == 201, response.text
    return response.json()


async def _confirm(stack: _Stack, boss: dict[str, str], probed: dict[str, Any]) -> dict[str, Any]:
    response = await stack.client.post(
        f"{BASE}/{probed['session_id']}/confirm", json={"fingerprint": probed["host_key"]["fingerprint"]}, headers=boss
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _spend_token(stack: _Stack) -> None:
    """Раннер на той стороне: тратит выданный токен, как при регистрации."""
    for _ in range(300):
        waiting = [t for t in await stack.tokens.list() if t.revoked_at is None and t.uses == 0]
        if waiting:
            await stack.tokens.consume(waiting[0].token_hash, datetime.now(UTC))
            return
        await asyncio.sleep(0.01)


async def _finished(stack: _Stack, job_id: str, boss: dict[str, str]) -> dict[str, Any]:
    for _ in range(400):
        job = (await stack.client.get(f"/api/admin/runner-install/jobs/{job_id}", headers=boss)).json()
        if job["state"] != "running":
            return job
        await asyncio.sleep(0.01)
    raise AssertionError("ssh install did not finish")


async def _install(stack: _Stack, boss: dict[str, str], probed: dict[str, Any], **extra: Any) -> dict[str, Any]:
    started = await stack.client.post(f"{BASE}/{probed['session_id']}/install", json=extra, headers=boss)
    assert started.status_code == 202, started.text
    spender = asyncio.create_task(_spend_token(stack))
    job = await _finished(stack, started.json()["id"], boss)
    await spender
    return job


def _audit_blob(stack: _Stack, entries: list[Any]) -> str:
    return str([(e.action, e.target, e.details) for e in entries])


async def test__ssh_probe__shows_fingerprint_and_sends_no_credentials(stack: _Stack) -> None:
    boss = await _admin(stack)

    response = await stack.client.post(f"{BASE}/probe", json=_probe_body(), headers=boss)

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["host_key"] == {"key_type": HOST_KEY.key_type, "fingerprint": HOST_KEY.fingerprint}
    assert PASSWORD not in response.text
    assert stack.ssh_host.connects == []
    assert stack.ssh_connector.fetched == [("203.0.113.10", 22)]
    audit = await stack.users.audit.list()
    assert [e.action for e in audit] == ["runner_install.ssh.probe"]
    assert PASSWORD not in _audit_blob(stack, audit)
    assert HOST_KEY.fingerprint in _audit_blob(stack, audit)


async def test__ssh_probe__blocked_addresses_never_reach_the_connector(stack: _Stack) -> None:
    boss = await _admin(stack)
    stack.ssh_egress.blocked = {
        "10.0.0.5": EgressBlockReason.private,
        "169.254.169.254": EgressBlockReason.metadata,
        "localhost": EgressBlockReason.loopback,
    }

    for host, reason in (("10.0.0.5", "private"), ("169.254.169.254", "metadata"), ("localhost", "loopback")):
        response = await stack.client.post(f"{BASE}/probe", json=_probe_body(host=host), headers=boss)
        assert response.status_code == 422
        assert response.json()["detail"] == {"code": "address_blocked", "reason": reason}

    assert stack.ssh_connector.fetched == []
    assert stack.ssh_host.connects == []


async def test__ssh_probe__policy_is_the_user_one_and_unresolved_names_are_reported(stack: _Stack) -> None:
    boss = await _admin(stack)

    ok = await stack.client.post(f"{BASE}/probe", json=_probe_body(), headers=boss)
    missing = await stack.client.post(f"{BASE}/probe", json=_probe_body(host="nope.example.org"), headers=boss)

    assert ok.status_code == 201
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "address_unresolved"
    assert {purpose.value for _, _, purpose in stack.ssh_egress.asked} == {"user"}


async def test__ssh_probe__unreachable_host_is_a_clear_error(stack: _Stack) -> None:
    boss = await _admin(stack)
    stack.ssh_host.unreachable = True

    response = await stack.client.post(f"{BASE}/probe", json=_probe_body(), headers=boss)

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "unreachable"}


async def test__ssh_probe__invalid_input_never_echoes_the_secret(stack: _Stack) -> None:
    boss = await _admin(stack)

    bad_user = await stack.client.post(f"{BASE}/probe", json=_probe_body(username="a b;rm"), headers=boss)
    bad_port = await stack.client.post(f"{BASE}/probe", json=_probe_body(port=70000), headers=boss)
    no_secret = await stack.client.post(
        f"{BASE}/probe", json={**_probe_body(), "password": None, "auth_kind": "password"}, headers=boss
    )
    no_key = await stack.client.post(f"{BASE}/probe", json={**_probe_body(), "auth_kind": "key"}, headers=boss)

    assert {bad_user.status_code, bad_port.status_code, no_secret.status_code, no_key.status_code} == {422}
    for response in (bad_user, bad_port, no_secret, no_key):
        assert PASSWORD not in response.text
    assert stack.ssh_connector.fetched == []


async def test__ssh_confirm__wrong_fingerprint_is_refused_and_nothing_is_sent(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)

    response = await stack.client.post(
        f"{BASE}/{probed['session_id']}/confirm", json={"fingerprint": "SHA256:somethingelse12345"}, headers=boss
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "fingerprint_mismatch"}
    assert stack.ssh_host.connects == []
    assert "runner_install.ssh.confirm_rejected" in [e.action for e in await stack.users.audit.list()]


async def test__ssh_confirm__logs_in_pinned_to_the_confirmed_key_and_returns_the_plan(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)

    plan = await _confirm(stack, boss, probed)

    address, target, pinned = stack.ssh_host.connects[0]
    assert address == "203.0.113.10"
    assert pinned.fingerprint == HOST_KEY.fingerprint
    assert target.username == "deploy"
    assert plan["system"] == {
        "os": "linux",
        "arch": "x86_64",
        "distro": "ubuntu",
        "has_docker": True,
        "docker_usable": True,
        "has_systemd": True,
        "is_root": True,
    }
    assert [(p["key"], p["action"]) for p in plan["plan"]] == [
        ("connect", "run"),
        ("token", "run"),
        ("docker", "skip"),
        ("service", "run"),
        ("verify", "run"),
        ("register", "run"),
    ]
    assert PASSWORD not in str(plan)


async def test__ssh_confirm__wrong_password_is_reported_without_leaking_it(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss, password="wrong-password")

    response = await stack.client.post(
        f"{BASE}/{probed['session_id']}/confirm", json={"fingerprint": probed["host_key"]["fingerprint"]}, headers=boss
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "auth_failed"}
    assert "wrong-password" not in response.text


async def test__ssh_session__belongs_to_the_admin_who_started_it(stack: _Stack) -> None:
    boss = await _admin(stack)
    other = await stack.users.add("other", admin=True)
    probed = await _probe(stack, boss)

    response = await stack.client.post(
        f"{BASE}/{probed['session_id']}/confirm", json={"fingerprint": probed["host_key"]["fingerprint"]}, headers=other
    )

    assert response.status_code == 404


async def test__ssh_install__requires_confirmation_first(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)

    response = await stack.client.post(f"{BASE}/{probed['session_id']}/install", json={}, headers=boss)

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "not_confirmed"}


async def test__ssh_install__success_keeps_the_token_off_the_command_line_and_wipes_credentials(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)
    await _confirm(stack, boss, probed)

    job = await _install(stack, boss, probed, name="Lab Box")

    assert job["state"] == "succeeded", job
    assert [(s["key"], s["state"]) for s in job["steps"]] == [
        ("connect", "done"),
        ("token", "done"),
        ("docker", "skipped"),
        ("service", "done"),
        ("verify", "done"),
        ("register", "done"),
    ]
    service = find_call(stack.ssh_host, "sh -s -- install")
    token = next(
        line.split("=", 1)[1].strip("'")
        for line in (service.stdin or "").splitlines()
        if line.startswith("HSE_RUNNER__TOKEN=")
    )
    assert token.startswith("hsrt_")
    assert all(token not in call.command for call in stack.ssh_host.calls)
    assert "HSE_RUNNER__API_URL=" in (service.stdin or "")
    assert "# runner install script for registry.example/hds:1.2.3" in (service.stdin or "")
    everything = str(job) + _audit_blob(stack, await stack.users.audit.list())
    assert token not in everything
    assert PASSWORD not in everything
    assert "runner_install.ssh.succeeded" in [e.action for e in await stack.users.audit.list()]
    assert stack.ssh_credentials.items == {}
    again = await stack.client.post(f"{BASE}/{probed['session_id']}/install", json={}, headers=boss)
    assert again.status_code == 404
    assert all(s.closed for s in stack.ssh_connector.sessions)


async def test__ssh_install__failure_revokes_the_token_and_the_session_allows_a_retry(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)
    await _confirm(stack, boss, probed)
    stack.ssh_host.fail_on = {"sh -s -- install": SshResult(1, "", "no space left on device")}

    failed = await _install(stack, boss, probed)

    assert failed["state"] == "failed"
    assert failed["error_code"] == "service_install_failed"
    assert failed["error_detail"] == "no space left on device"
    assert [s["state"] for s in failed["steps"]][:4] == ["done", "done", "skipped", "failed"]
    assert all(t.revoked_at is not None for t in await stack.tokens.list())

    stack.ssh_host.fail_on = {}
    retried = await _install(stack, boss, probed)

    assert retried["state"] == "succeeded", (retried["error_code"], retried["error_detail"], retried["steps"])


async def test__ssh_install__missing_docker_needs_an_explicit_choice(stack: _Stack) -> None:
    boss = await _admin(stack)
    stack.ssh_host.recon = LINUX_RECON.replace("has_docker=1", "has_docker=0").replace("docker_ok=1", "docker_ok=0")
    probed = await _probe(stack, boss)
    plan = await _confirm(stack, boss, probed)

    refused = await stack.client.post(f"{BASE}/{probed['session_id']}/install", json={}, headers=boss)
    job = await _install(stack, boss, probed, install_docker=True)

    assert ("docker", "install_docker") in [(p["key"], p["action"]) for p in plan["plan"]]
    assert refused.status_code == 422
    assert refused.json()["detail"] == {"code": "docker_missing"}
    assert job["state"] == "succeeded"
    installer = find_call(stack.ssh_host, "get.docker.com")
    assert shlex.split(installer.command)[-1] == "curl -fsSL https://get.docker.com | sh"


async def test__ssh_install__non_root_without_sudo_is_blocked_with_sudo_it_uses_the_password_on_stdin(
    stack: _Stack,
) -> None:
    boss = await _admin(stack)
    stack.ssh_host.recon = LINUX_RECON.replace("uid=0", "uid=1000")
    blocked = await _probe(stack, boss)
    await _confirm(stack, boss, blocked)
    refused = await stack.client.post(f"{BASE}/{blocked['session_id']}/install", json={}, headers=boss)

    probed = await _probe(stack, boss, sudo=True)
    await _confirm(stack, boss, probed)
    job = await _install(stack, boss, probed)

    assert refused.status_code == 422
    assert refused.json()["detail"] == {"code": "plan_blocked"}
    assert job["state"] == "succeeded"
    service = find_call(stack.ssh_host, "sh -s -- install")
    assert service.command == "sudo -S -p '' sh -s -- install"
    assert (service.stdin or "").startswith(PASSWORD + "\n")
    assert PASSWORD not in service.command


async def test__ssh_install__key_auth_uses_non_interactive_sudo(stack: _Stack) -> None:
    boss = await _admin(stack)
    stack.ssh_host.recon = LINUX_RECON.replace("uid=0", "uid=1000")
    body = {"auth_kind": "key", "private_key": PRIVATE_KEY, "passphrase": "pp", "sudo": True}
    response = await stack.client.post(
        f"{BASE}/probe", json={k: v for k, v in {**_probe_body(), **body}.items() if k != "password"}, headers=boss
    )
    probed = response.json()
    await _confirm(stack, boss, probed)

    job = await _install(stack, boss, probed)

    assert job["state"] == "succeeded", job
    assert find_call(stack.ssh_host, "sh -s -- install").command == "sudo -n sh -s -- install"
    assert "SECRETKEYBODY" not in str(job) + _audit_blob(stack, await stack.users.audit.list())


async def test__ssh_install__unsupported_os_is_blocked(stack: _Stack) -> None:
    boss = await _admin(stack)
    stack.ssh_host.recon = "os=FreeBSD\narch=amd64\nuid=0\n"
    probed = await _probe(stack, boss)
    plan = await _confirm(stack, boss, probed)

    refused = await stack.client.post(f"{BASE}/{probed['session_id']}/install", json={}, headers=boss)

    assert ("service", "blocked") in [(p["key"], p["action"]) for p in plan["plan"]]
    assert refused.status_code == 422
    assert refused.json()["detail"] == {"code": "plan_blocked"}


async def test__ssh_cancel__wipes_the_session(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)

    cancelled = await stack.client.delete(f"{BASE}/{probed['session_id']}", headers=boss)
    after = await stack.client.post(
        f"{BASE}/{probed['session_id']}/confirm", json={"fingerprint": probed["host_key"]["fingerprint"]}, headers=boss
    )

    assert cancelled.status_code == 204
    assert after.status_code == 404


async def test__ssh_saved_credentials__not_stored_unless_asked(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss)
    await _confirm(stack, boss, probed)

    await _install(stack, boss, probed)

    assert stack.ssh_credentials.items == {}
    listed = (await stack.client.get(f"{BASE}/credentials", headers=boss)).json()
    assert listed == []


async def test__ssh_saved_credentials__stored_once_listed_without_values_and_deletable(stack: _Stack) -> None:
    boss = await _admin(stack)
    probed = await _probe(stack, boss, save_credentials=True, label="Лаборатория")
    await _confirm(stack, boss, probed)

    job = await _install(stack, boss, probed)
    listing = await stack.client.get(f"{BASE}/credentials", headers=boss)

    assert job["state"] == "succeeded"
    assert len(stack.ssh_credentials.items) == 1
    item = listing.json()[0]
    assert listing.headers["cache-control"] == "no-store"
    assert item["label"] == "Лаборатория"
    assert item["fingerprint"] == HOST_KEY.fingerprint
    assert item["auth_kind"] == "password"
    assert PASSWORD not in listing.text
    assert set(item) == {
        "id", "label", "host", "port", "username", "sudo", "auth_kind", "key_type", "fingerprint",
        "created_at", "last_used_at", "runner_name",
    }  # fmt: skip
    audit = await stack.users.audit.list()
    assert "runner_install.ssh.credentials_save" in [e.action for e in audit]
    assert PASSWORD not in _audit_blob(stack, audit)

    deleted = await stack.client.delete(f"{BASE}/credentials/{item['id']}", headers=boss)
    missing = await stack.client.delete(f"{BASE}/credentials/{item['id']}", headers=boss)

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert (await stack.client.get(f"{BASE}/credentials", headers=boss)).json() == []
    assert "runner_install.ssh.credentials_delete" in [e.action for e in await stack.users.audit.list()]


async def _saved(stack: _Stack, boss: dict[str, str]) -> str:
    probed = await _probe(stack, boss, save_credentials=True)
    await _confirm(stack, boss, probed)
    assert (await _install(stack, boss, probed))["state"] == "succeeded"
    stack.ssh_host.calls.clear()
    stack.ssh_host.connects.clear()
    return next(iter(stack.ssh_credentials.items))


async def test__ssh_saved_credentials__update_in_one_click_without_waiting_for_a_new_registration(
    stack: _Stack,
) -> None:
    boss = await _admin(stack)
    credential_id = await _saved(stack, boss)

    started = await stack.client.post(
        f"{BASE}/credentials/{credential_id}/run", json={"action": "update"}, headers=boss
    )
    job = await _finished(stack, started.json()["id"], boss)

    assert started.status_code == 202
    assert job["state"] == "succeeded", job
    assert next(s for s in job["steps"] if s["key"] == "register")["state"] == "skipped"
    assert [c.command for c in stack.ssh_host.calls if "uninstall" in c.command] == []
    assert stack.ssh_host.connects[0][2].fingerprint == HOST_KEY.fingerprint
    assert stack.ssh_credentials.used[-1][0] == credential_id


async def test__ssh_saved_credentials__reinstall_purges_and_registers_again(stack: _Stack) -> None:
    boss = await _admin(stack)
    credential_id = await _saved(stack, boss)

    started = await stack.client.post(
        f"{BASE}/credentials/{credential_id}/run", json={"action": "reinstall"}, headers=boss
    )
    spender = asyncio.create_task(_spend_token(stack))
    job = await _finished(stack, started.json()["id"], boss)
    await spender

    assert job["state"] == "succeeded", job
    assert any(c.command.endswith("uninstall --purge") for c in stack.ssh_host.calls)
    assert next(s for s in job["steps"] if s["key"] == "register")["state"] == "done"


async def test__ssh_saved_credentials__changed_host_key_stops_before_any_login(stack: _Stack) -> None:
    boss = await _admin(stack)
    credential_id = await _saved(stack, boss)
    stack.ssh_host.host_key = HOST_KEY.__class__(
        "ssh-ed25519", "SHA256:attackerkey000000000000000000000000000000", "ssh-ed25519 EVIL"
    )

    started = await stack.client.post(
        f"{BASE}/credentials/{credential_id}/run", json={"action": "update"}, headers=boss
    )
    job = await _finished(stack, started.json()["id"], boss)

    assert job["state"] == "failed"
    assert job["error_code"] == "host_key_changed"
    assert stack.ssh_host.calls == []
    assert PASSWORD not in str(job)


async def test__ssh_saved_credentials__run_unknown_id_is_404(stack: _Stack) -> None:
    boss = await _admin(stack)

    response = await stack.client.post(f"{BASE}/credentials/nope/run", json={"action": "update"}, headers=boss)

    assert response.status_code == 404


async def test__ssh_saved_credentials__saved_target_is_checked_by_the_policy_again(stack: _Stack) -> None:
    boss = await _admin(stack)
    credential_id = await _saved(stack, boss)
    stack.ssh_egress.blocked = {"srv.example.org": EgressBlockReason.private}

    response = await stack.client.post(
        f"{BASE}/credentials/{credential_id}/run", json={"action": "update"}, headers=boss
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "address_blocked"
    assert stack.ssh_host.connects == []


async def test__ssh_probe__is_rate_limited_per_admin_and_per_host(stack: _Stack) -> None:
    boss = await _admin(stack)
    stack.app.state.rate_limiter = InMemoryRateLimiter()

    codes = [(await stack.client.post(f"{BASE}/probe", json=_probe_body(), headers=boss)).status_code for _ in range(7)]

    assert codes[:5] == [201] * 5
    assert codes[5] == 429
    other_host = await stack.client.post(
        f"{BASE}/probe", json=_probe_body(host="srv.example.org", port=2222), headers=boss
    )
    assert other_host.status_code == 201
    stack.ssh_egress.table["other.example.org"] = ("203.0.113.11",)
    elsewhere = await stack.client.post(f"{BASE}/probe", json=_probe_body(host="other.example.org"), headers=boss)
    assert elsewhere.status_code == 201


async def test__ssh_capability__reports_what_the_ui_may_offer(stack: _Stack) -> None:
    boss = await _admin(stack)

    response = await stack.client.get(BASE, headers=boss)

    assert response.json() == {"enabled": True, "can_save_credentials": True}
