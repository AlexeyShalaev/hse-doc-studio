from __future__ import annotations

import copy
import pickle
from dataclasses import dataclass

import pytest
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.jobs.codec import encode

_CANARY = "ghp_CANARYtokenValue1234567890abcdef"


def test__secret__repr_str_and_format__are_masked() -> None:
    secret = Secret(_CANARY)

    assert repr(secret) == "Secret(***)"
    assert str(secret) == "Secret(***)"
    assert f"{secret}" == "Secret(***)"
    assert _CANARY not in f"{[secret]} { ({'k': secret}) }"


def test__secret__reveal__returns_the_text() -> None:
    assert Secret(_CANARY).reveal() == _CANARY


def test__secret__equality__compares_values_and_ignores_other_types() -> None:
    assert Secret("a") == Secret("a")
    assert Secret("a") != Secret("b")
    assert Secret("a") != "a"


def test__secret__bool__is_false_only_when_empty() -> None:
    assert Secret("x")
    assert not Secret("")


def test__secret__hash__is_refused() -> None:
    with pytest.raises(TypeError):
        hash(Secret("a"))


@pytest.mark.parametrize("operation", [pickle.dumps, copy.copy, copy.deepcopy])
def test__secret__pickle_and_copy__are_refused(operation) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TypeError, match="Secret"):
        operation(Secret(_CANARY))


@dataclass(frozen=True)
class _Payload:
    token: Secret


def test__secret__job_codec__refuses_to_send_it_in_a_job() -> None:
    with pytest.raises(TypeError, match="Secret"):
        encode(_Payload(Secret(_CANARY)))
