import json

import pytest
from hse_doc_studio.core.identity.redaction import REDACTED, is_secret_key, redact
from hypothesis import given
from hypothesis import strategies as st


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


_SECRET_VALUE = "hse_Zq9-SECRET-" + "x" * 12
_KEYS = st.one_of(
    st.sampled_from(["token", "X-Auth-Token", "client_secret", "NewPassword", "api_key", "cookie", "Authorization"]),
    st.text(alphabet="abcxyz_-", min_size=1, max_size=8),
)


def _details(leaf: st.SearchStrategy[object]) -> st.SearchStrategy[object]:
    return st.recursive(
        leaf,
        lambda inner: st.one_of(st.lists(inner, max_size=3), st.dictionaries(_KEYS, inner, max_size=4)),
        max_leaves=12,
    )


@given(_details(st.just(_SECRET_VALUE)))
def test__redact__fuzz_secret_value_under_secret_key__never_survives(details: object) -> None:
    # Строим структуру, где значение-секрет стоит только под секретными ключами, остальное заменено.
    def only_under_secret(node: object, *, under_secret: bool = False) -> object:
        if isinstance(node, dict):
            return {k: only_under_secret(v, under_secret=under_secret or is_secret_key(k)) for k, v in node.items()}
        if isinstance(node, list):
            return [only_under_secret(v, under_secret=under_secret) for v in node]
        return node if under_secret else "plain"

    prepared = only_under_secret(details)
    if not isinstance(prepared, dict):
        prepared = {"token": prepared}

    assert _SECRET_VALUE not in json.dumps(redact(prepared))
