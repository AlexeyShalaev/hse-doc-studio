from __future__ import annotations

import pytest
from hse_doc_studio.core.git_sync.error_messages import _MESSAGES, git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.i18n import set_interface_language


@pytest.fixture(autouse=True)
def _reset_language() -> None:
    set_interface_language(None)


@pytest.mark.parametrize("code", sorted(_MESSAGES, key=lambda c: c.value))
def test__git_error__known_code__has_both_languages(code: GitErrorCode) -> None:
    set_interface_language("ru")
    ru = git_error(code).detail
    set_interface_language("en")
    en = git_error(code).detail

    assert ru != en
    assert ru != code.value
    assert en != code.value
    assert git_error(code).code is code


def test__git_error__git_error_code__detail_is_the_scrubbed_tail() -> None:
    error = git_error(GitErrorCode.git_error, tail="fatal: odd")

    assert error.detail == "fatal: odd"


def test__git_error__git_error_without_tail__generic_text() -> None:
    assert git_error(GitErrorCode.git_error).detail not in {"", "git_error"}


def test__git_error__extra_context__kept() -> None:
    assert git_error(GitErrorCode.sync_busy, operation_id="op1").ctx == {"operation_id": "op1"}
