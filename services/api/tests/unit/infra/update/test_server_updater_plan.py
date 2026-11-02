from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest
from hse_doc_studio.infra.update.server_updater import plan
from hse_doc_studio.infra.update.server_updater.client import ApiUnavailableError, HttpApi
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig
from hse_doc_studio.infra.update.server_updater.journal import Journal

DIGEST = "sha256:" + "c" * 64


@pytest.mark.parametrize(
    ("ref", "repo", "tag"),
    [
        ("ghcr.io/a/b:0.3.1", "ghcr.io/a/b", "0.3.1"),
        ("ghcr.io/a/b", "ghcr.io/a/b", "latest"),
        ("localhost:5000/b:1.0.0", "localhost:5000/b", "1.0.0"),
        ("localhost:5000/b", "localhost:5000/b", "latest"),
        (f"ghcr.io/a/b:0.3.1@{DIGEST}", "ghcr.io/a/b", "0.3.1"),
    ],
)
def test__split_image(ref: str, repo: str, tag: str) -> None:
    assert plan.split_image(ref) == (repo, tag)
    assert plan.target_ref(ref, "0.4.0") == f"{repo}:0.4.0"
    assert plan.rollback_ref(ref) == f"{repo}:rollback-prev"


def test__digest_doc_accepts_only_matching_version_and_wellformed_digest() -> None:
    ok = json.dumps({"version": "v0.4.0", "digest": DIGEST})
    assert plan.parse_digest_doc(ok, version="0.4.0") == DIGEST
    assert plan.parse_digest_doc(ok, version="0.4.1") is None
    assert plan.parse_digest_doc(json.dumps({"version": "0.4.0", "digest": "sha256:short"}), version="0.4.0") is None
    assert plan.parse_digest_doc("not json", version="0.4.0") is None
    assert plan.parse_digest_doc("[]", version="0.4.0") is None


def test__digest_matches_checks_repo_and_value() -> None:
    inspect = {"RepoDigests": [f"ghcr.io/a/b@{DIGEST}", f"other/b@sha256:{'d' * 64}"]}
    assert plan.digest_matches(inspect, "ghcr.io/a/b", DIGEST)
    assert not plan.digest_matches(inspect, "ghcr.io/a/b", "sha256:" + "d" * 64)
    assert not plan.digest_matches({}, "ghcr.io/a/b", DIGEST)


def test__cosign_command_pins_workflow_identity_and_digest() -> None:
    cmd = plan.cosign_verify_command("ghcr.io/a/b", DIGEST)
    assert cmd[-1] == f"ghcr.io/a/b@{DIGEST}"
    assert plan.COSIGN_ISSUER in cmd
    assert "--certificate-identity-regexp" in cmd
    assert "publish\\.yml" in cmd[cmd.index("--certificate-identity-regexp") + 1]


def container(**host: Any) -> dict[str, Any]:
    return {
        "Id": "abcdef1234567890",
        "Name": "/stack-api-1",
        "Config": {
            "Image": "ghcr.io/a/b:0.3.1",
            "Env": ["A=1", "PATH=/x", "HOSTNAME=abc", "PY=1"],
            "Labels": {"com.docker.compose.project": "stack", "other": "x"},
            "Healthcheck": {
                "Test": ["CMD", "curl", "-f", "http://localhost:8000/health"],
                "Interval": 10_000_000_000,
                "Retries": 10,
            },
            "User": "",
            "Cmd": ["hse-doc-studio", "runner"],
        },
        "HostConfig": {
            "NetworkMode": "stack_default",
            "RestartPolicy": {"Name": "unless-stopped"},
            "PortBindings": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "17240"}]},
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "10m", "max-file": "5"}},
            "GroupAdd": ["998"],
            **host,
        },
        "Mounts": [{"Name": "api-data", "Destination": "/data", "RW": True}],
        "NetworkSettings": {"Networks": {"stack_default": {"Aliases": ["api", "abcdef123456", "stack-api-1"]}}},
    }


def test__recreate_command_keeps_everything_that_compose_set() -> None:
    image = {"Config": {"Env": ["PY=1"], "Cmd": None}}
    cmd = plan.recreate_command(container(), image, "ghcr.io/a/b:0.4.0")

    assert cmd[:4] == ["run", "-d", "--name", "stack-api-1"]
    assert cmd[cmd.index("--restart") : cmd.index("--restart") + 2] == ["--restart", "unless-stopped"]
    assert "--network-alias" in cmd
    assert "api" in cmd
    assert "abcdef123456" not in cmd  # сервис резолвится по имени, id контейнера нет
    assert cmd[cmd.index("-p") : cmd.index("-p") + 2] == ["-p", "127.0.0.1:17240:8000/tcp"]
    assert cmd[cmd.index("-v") : cmd.index("-v") + 2] == ["-v", "api-data:/data"]
    assert "com.docker.compose.project=stack" in cmd
    assert "other=x" not in cmd
    assert cmd[cmd.index("-e") : cmd.index("-e") + 2] == ["-e", "A=1"]
    assert "PATH=/x" not in cmd
    assert "HOSTNAME=abc" not in cmd
    assert "PY=1" not in cmd
    assert "--health-cmd" in cmd
    assert "--health-retries" in cmd
    assert cmd[cmd.index("--log-opt") : cmd.index("--log-opt") + 2] == ["--log-opt", "max-size=10m"]
    assert "--group-add" in cmd
    assert "998" in cmd
    assert cmd[-3:] == ["ghcr.io/a/b:0.4.0", "hse-doc-studio", "runner"]


def test__recreate_keeps_a_disabled_healthcheck_disabled() -> None:
    # раннер и апдейтер без HTTP: проверка образа (curl :8000) у них вечно unhealthy, compose её отключает
    c = container()
    c["Config"]["Healthcheck"] = {"Test": ["NONE"]}
    cmd = plan.recreate_command(c, {"Config": {}}, "ghcr.io/a/b:0.4.0")
    assert "--no-healthcheck" in cmd
    assert "--health-cmd" not in cmd


def test__unsupported_options_are_listed_and_defaults_ignored() -> None:
    assert plan.unsupported_options(container()) == []
    assert plan.unsupported_options(container(Privileged=True, CapAdd=["NET_ADMIN"], ShmSize=67108864)) == [
        "Privileged",
        "CapAdd",
    ]


def test__oneshot_command_runs_in_the_api_network_with_its_env_file() -> None:
    cmd = plan.oneshot_command(
        "img", ["hse-doc-studio", "db", "current"], network="n", env_file="/e", snapshot_volume="v"
    )
    assert cmd == [
        "run",
        "--rm",
        "--network",
        "n",
        "--env-file",
        "/e",
        "-v",
        "v:/snap",
        "img",
        "hse-doc-studio",
        "db",
        "current",
    ]


def test__env_file_drops_runtime_noise_and_multiline_values() -> None:
    text = plan.env_file_text(["A=1", "PATH=/x", "HOSTNAME=h", "B=line1\nline2", "C=3"])
    assert text == "A=1\nC=3\n"


def test__parse_db_current_and_env_tag() -> None:
    assert plan.parse_db_current("current: r1\nhead: r2\n") == ("r1", "r2")
    assert plan.parse_db_current("current: -\nhead: r2") == (None, "r2")
    assert plan.set_env_tag("A=1\nTAG=0.3.1\nB=2", "0.4.0") == "A=1\nTAG=0.4.0\nB=2\n"
    assert plan.set_env_tag("A=1", "0.4.0") == "A=1\nTAG=0.4.0\n"
    assert plan.is_version("0.4.0")
    assert not plan.is_version("latest")
    assert not plan.is_version("0.4.0; rm -rf /")


def test__config_requires_token_and_parses_env(tmp_path: Any) -> None:
    with pytest.raises(ValueError, match="TOKEN"):
        UpdaterConfig.from_env({})
    cfg = UpdaterConfig.from_env({"HSE_UPDATER__TOKEN": "t", "HSE_UPDATER__SERVICES": "api, runner ,ocr"})
    assert cfg.services == ("api", "runner", "ocr")
    assert cfg.health_url.endswith("/health/ready")


def test__journal_roundtrip_survives_garbage_and_orders_the_outbox(tmp_path: Any) -> None:
    path = tmp_path / "j.json"
    j = Journal(path)
    j.start_run({"id": "r", "seq": 0})
    j.push_event("r", {"seq": j.next_seq()})
    j.push_event("r", {"seq": j.next_seq()})
    again = Journal(path)
    assert [i["event"]["seq"] for i in again.outbox] == [1, 2]
    assert again.run is not None
    again.pop_event()
    assert [i["event"]["seq"] for i in Journal(path).outbox] == [2]
    path.write_text("{broken", encoding="utf-8")
    assert Journal(path).run is None


def test__http_api_drops_events_of_a_run_the_api_does_not_know(monkeypatch: pytest.MonkeyPatch) -> None:
    # найдено на живом docker: после восстановления базы из снимка записи самого отката в ней нет, 404 на его события
    # не должен вечно держать очередь журнала
    api = HttpApi("http://api:8000", "t", "0.1.0")

    def not_found(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", not_found)
    api.post_event("run", {"seq": 1})  # не бросает: событию некуда доставляться

    def unavailable(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError("u", 503, "Unavailable", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    with pytest.raises(ApiUnavailableError):
        api.post_event("run", {"seq": 1})
