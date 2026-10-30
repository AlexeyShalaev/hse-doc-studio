"""Контракт раннера: contracts/runner (openapi, коды, эталоны) против pydantic-схем и проводных датаклассов.

Форму меняют так: сначала openapi и эталоны, затем `api/schemas/runner.py` и `core/jobs/wire.py`
с их тестами в одном коммите.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.api.schemas import runner as schemas
from hse_doc_studio.core.jobs import wire
from hse_doc_studio.core.jobs.codec import (
    decode,
    decode_envelope,
    decode_poll_response,
    encode,
    encode_envelope,
    encode_poll_response,
)
from hse_doc_studio.core.jobs.enums import JobKind, RunnerErrorCode
from hse_doc_studio.core.jobs.files import ArtifactRef, ManifestFile
from pydantic import BaseModel

_CONTRACT = Path(__file__).resolve().parents[5] / "contracts" / "runner"
_FIXTURES = _CONTRACT / "fixtures"

# Схема -> как разобрать эталон проводной моделью и собрать обратно; None значит у схемы нет датакласса.
# Вложенные схемы: отдельных эталонов нет, их покрывают объемлющие.
_NESTED = {"ActorWire", "JobSpecWire", "JobResultWire", "BlobLocationBody", "DeclaredAiEndpointBody", "RelayEventBody"}


def _encode_poll_request(request: wire.PollRequest) -> Any:
    # Раннер без возможности `ai_slots` поле не шлёт: эталон старого раннера остаётся без него.
    body = encode(request)
    assert isinstance(body, dict)
    if request.free_ai_slots == 0:
        body.pop("free_ai_slots")
    return body


_WIRE: dict[str, tuple[Callable[[Any], Any], Callable[[Any], Any]] | None] = {
    "ManifestEntry": (lambda d: decode(ManifestFile, d), encode),
    "ArtifactRefBody": (lambda d: decode(ArtifactRef, d), encode),
    "JobEnvelopeBody": (decode_envelope, encode_envelope),
    "PollResponseBody": (decode_poll_response, encode_poll_response),
    "RunnerRegisterRequestBody": (lambda d: decode(wire.RunnerRegisterRequest, d), encode),
    "RunnerRegisterResponseBody": (lambda d: decode(wire.RunnerRegisterResponse, d), encode),
    "PollRequestBody": (lambda d: decode(wire.PollRequest, d), _encode_poll_request),
    "HeartbeatRequestBody": (lambda d: decode(wire.HeartbeatRequest, d), encode),
    "HeartbeatResponseBody": (lambda d: decode(wire.HeartbeatResponse, d), encode),
    "LogBatchBody": (lambda d: decode(wire.LogBatch, d), encode),
    "BlobNeedRequestBody": (lambda d: decode(wire.BlobNeedRequest, d), encode),
    "BlobNeedResponseBody": (lambda d: decode(wire.BlobNeedResponse, d), encode),
    "ArtifactUploadRequestBody": (lambda d: decode(wire.ArtifactUploadRequest, d), encode),
    "ArtifactUploadResponseBody": (lambda d: decode(wire.ArtifactUploadResponse, d), encode),
    "CompleteRequestBody": (lambda d: decode(wire.CompleteRequest, d), encode),
    "CompleteResponseBody": (lambda d: decode(wire.CompleteResponse, d), encode),
    "RunnerErrorBody": None,
    "RunnerAnnounceRequestBody": (lambda d: decode(wire.RunnerAnnounceRequest, d), encode),
    "RunnerAnnounceResponseBody": (lambda d: decode(wire.RunnerAnnounceResponse, d), encode),
    "RunnerPairStartRequestBody": (lambda d: decode(wire.RunnerPairStartRequest, d), encode),
    "RunnerPairStartResponseBody": (lambda d: decode(wire.RunnerPairStartResponse, d), encode),
    "RunnerPairPollRequestBody": (lambda d: decode(wire.RunnerPairPollRequest, d), encode),
    "RunnerPairPollResponseBody": (lambda d: decode(wire.RunnerPairPollResponse, d), encode),
    "RelayEventBatchBody": (lambda d: decode(wire.RelayEventBatch, d), encode),
    "RelayEventAckBody": (lambda d: decode(wire.RelayEventAck, d), encode),
}


def _models() -> dict[str, type[BaseModel]]:
    return {
        name: cls
        for name, cls in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(cls, BaseModel) and cls.__module__ == schemas.__name__ and cls is not schemas.StrictModel
    }


def _openapi() -> dict[str, Any]:
    return yaml.safe_load((_CONTRACT / "openapi.yaml").read_text(encoding="utf-8"))


def _refs(node: Any):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def _enums(schema: dict[str, Any]) -> dict[str, list[Any]]:
    found: dict[str, list[Any]] = {}
    for name, prop in schema.get("properties", {}).items():
        for node in [prop, *prop.get("anyOf", [])]:
            if "enum" in node:
                found[name] = node["enum"]
    return found


def _fixtures(schema: str) -> list[Path]:
    return sorted((_FIXTURES / schema).glob("*.json"))


def test__openapi__declares_exactly_the_pydantic_schemas() -> None:
    assert set(_openapi()["components"]["schemas"]) == set(_models())


@pytest.mark.parametrize("name", sorted(_models()))
def test__openapi__schema_matches_pydantic_model(name: str) -> None:
    declared = _openapi()["components"]["schemas"][name]
    generated = _models()[name].model_json_schema()
    assert set(declared["properties"]) == set(generated["properties"])
    assert set(declared.get("required", [])) == set(generated.get("required", []))
    assert declared.get("additionalProperties") is False
    assert _enums(declared) == _enums(generated)


def test__openapi__every_ref_resolves() -> None:
    spec = _openapi()
    for ref in _refs(spec):
        node: Any = spec
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]


def test__openapi__every_operation_has_a_documented_error_and_security() -> None:
    for path, item in _openapi()["paths"].items():
        for method, operation in item.items():
            assert operation["security"], f"{method} {path}"
            assert operation["operationId"], f"{method} {path}"
            if path != "/poll":
                assert any(code.startswith("4") for code in operation["responses"]), f"{method} {path}"


def test__error_codes__file_enum_and_openapi_agree() -> None:
    codes = json.loads((_CONTRACT / "error_codes.json").read_text(encoding="utf-8"))
    assert codes == [code.value for code in RunnerErrorCode]
    assert _openapi()["x-error-codes"] == codes
    assert len(set(codes)) == len(codes)


def test__openapi__defaults_match_wire_constants() -> None:
    defaults = _openapi()["x-defaults"]
    assert defaults == {
        "lease_s": wire.DEFAULT_LEASE_S,
        "heartbeat_s": wire.DEFAULT_HEARTBEAT_S,
        "max_poll_wait_s": wire.MAX_POLL_WAIT_S,
    }
    assert (
        _openapi()["servers"][0]["url"]
        == wire.RUNNER_API_PREFIX.removesuffix("/v1") + f"/v{wire.RUNNER_PROTOCOL_VERSION}"
    )


def test__fixtures__every_directory_has_a_schema_and_every_schema_a_fixture() -> None:
    directories = {path.name for path in _FIXTURES.iterdir() if path.is_dir()}
    assert directories == set(_models()) - _NESTED


def test__wire__every_schema_is_classified() -> None:
    assert set(_models()) - _NESTED == set(_WIRE)


@pytest.mark.parametrize(
    ("schema", "path"),
    [(schema, path) for schema in sorted(_WIRE) for path in _fixtures(schema)],
    ids=lambda value: value.stem if isinstance(value, Path) else value,
)
def test__fixtures__validate_and_round_trip_through_the_wire_model(schema: str, path: Path) -> None:
    body = json.loads(path.read_text(encoding="utf-8"))
    _models()[schema].model_validate(body)
    pair = _WIRE[schema]
    if pair is not None:
        parse, dump = pair
        assert dump(parse(body)) == body


def test__fixtures__envelope_covers_every_job_kind() -> None:
    kinds = {json.loads(path.read_text(encoding="utf-8"))["spec"]["kind"] for path in _fixtures("JobEnvelopeBody")}
    assert kinds == {kind.value for kind in JobKind}


def test__models__reject_unknown_fields() -> None:
    body = json.loads(next(iter(_fixtures("LogBatchBody"))).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="extra"):
        schemas.LogBatchBody.model_validate({**body, "surprise": 1})


def test__error_codes__personal_runner_codes_are_listed() -> None:
    codes = json.loads((_CONTRACT / "error_codes.json").read_text(encoding="utf-8"))
    assert {"runner_limit", "relay_request_gone", "relay_out_of_order", "relay_too_large", "slow_down"} <= set(codes)


def test__wire__server_features_are_the_announced_capabilities() -> None:
    body = json.loads((_FIXTURES / "RunnerAnnounceResponseBody" / "default.json").read_text(encoding="utf-8"))
    assert set(body["server_features"]) == wire.SERVER_FEATURES


def test__models__poll_without_any_free_slot_is_rejected() -> None:
    with pytest.raises(ValueError, match="free slot"):
        schemas.PollRequestBody.model_validate({"wait_s": 1, "free_slots": 0})
    with pytest.raises(ValueError, match="free slot"):
        wire.PollRequest(wait_s=1, free_slots=0, free_ai_slots=0)


def test__models__announce_rejects_duplicate_endpoint_names() -> None:
    body = json.loads((_FIXTURES / "RunnerAnnounceRequestBody" / "desktop.json").read_text(encoding="utf-8"))
    body["ai_endpoints"] = [{"name": "ollama", "flavor": "ollama"}] * 2
    with pytest.raises(ValueError, match="unique"):
        schemas.RunnerAnnounceRequestBody.model_validate(body)
    with pytest.raises(ValueError, match="unique"):
        decode(wire.RunnerAnnounceRequest, body)
