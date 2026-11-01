import re

from hse_doc_studio.core.device_codes import (
    USER_CODE_ALPHABET,
    new_device_secret,
    new_user_code,
    normalize_user_code,
)
from hse_doc_studio.core.jobs import pairing


def test__new_user_code__two_halves_from_alphabet() -> None:
    code = new_user_code()

    assert re.fullmatch(rf"[{USER_CODE_ALPHABET}]{{4}}-[{USER_CODE_ALPHABET}]{{4}}", code)


def test__normalize_user_code__case_spaces_dash_ignored_bad_none() -> None:
    assert normalize_user_code(" bcdf 2345 ") == "BCDF-2345"
    assert normalize_user_code("bcdf-2345") == "BCDF-2345"
    assert normalize_user_code("BCDF-234") is None
    assert normalize_user_code("AEIO-0001") is None


def test__new_device_secret__prefix_and_entropy() -> None:
    secret = new_device_secret("hsdv_")

    assert secret.startswith("hsdv_")
    assert len(secret) >= len("hsdv_") + 43
    assert new_device_secret("hsdv_") != secret


def test__runner_pairing__reexports_same_helpers_and_keeps_prefix() -> None:
    assert pairing.new_user_code is new_user_code
    assert pairing.normalize_user_code is normalize_user_code
    assert pairing.new_device_code().startswith("hsdc_")
