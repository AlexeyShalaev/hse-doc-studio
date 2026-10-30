from __future__ import annotations

import pytest
from hse_doc_studio.core.jobs.pairing import USER_CODE_ALPHABET, new_device_code, new_user_code, normalize_user_code


def test__user_code__shape_and_alphabet_without_lookalikes() -> None:
    codes = {new_user_code() for _ in range(200)}
    assert len(codes) > 190
    for code in codes:
        assert len(code) == 9
        assert code[4] == "-"
        assert set(code.replace("-", "")) <= set(USER_CODE_ALPHABET)
    assert not set("AEIOU01") & set(USER_CODE_ALPHABET)


@pytest.mark.parametrize("raw", ["bcdf-2345", "BCDF2345", " bcdf 2345 ", "Bcdf-2345"])
def test__normalize_user_code__ignores_case_spaces_and_dash(raw: str) -> None:
    assert normalize_user_code(raw) == "BCDF-2345"


@pytest.mark.parametrize("raw", ["", "BCDF-234", "BCDF-23450", "AAAA-BBBB", "BCDF-23O5"])
def test__normalize_user_code__rejects_foreign_codes(raw: str) -> None:
    assert normalize_user_code(raw) is None


def test__device_code__is_long_and_prefixed() -> None:
    code = new_device_code()
    assert code.startswith("hsdc_")
    assert len(code) > 40
