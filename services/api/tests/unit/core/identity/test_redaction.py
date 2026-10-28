import pytest
from hse_doc_studio.core.identity.redaction import REDACTED, is_secret_key, redact


@pytest.mark.parametrize(
    "name", ["password", "new_password", "Token", "access_token", "client_secret", "api_key", "Authorization", "cookie"]
)
def test__is_secret_key__secret_names__true(name: str) -> None:
    assert is_secret_key(name)


@pytest.mark.parametrize("name", ["email", "action", "ip", "name", "target"])
def test__is_secret_key__plain_names__false(name: str) -> None:
    assert not is_secret_key(name)


def test__redact__nested_structures__hides_values_not_keys() -> None:
    result = redact({"ok": 1, "password": "x", "items": [{"secret": "y", "n": 2}], "deep": {"token": "t", "a": "b"}})
    assert result == {
        "ok": 1,
        "password": REDACTED,
        "items": [{"secret": REDACTED, "n": 2}],
        "deep": {"token": REDACTED, "a": "b"},
    }


def test__redact__does_not_mutate_input() -> None:
    source = {"password": "x", "nested": {"token": "t"}}
    redact(source)
    assert source == {"password": "x", "nested": {"token": "t"}}


def test__redact__non_json_values__become_strings() -> None:
    assert redact({"v": object}) == {"v": str(object)}
    assert redact(("a", 1, None, True)) == ["a", 1, None, True]
