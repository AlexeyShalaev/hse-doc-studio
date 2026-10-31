"""Причина падения рана при отказах ИИ-шлюза: человеческий текст и код для интерфейса."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.ai_gateway.errors import AiModelNotAllowedError, AiProviderUnavailableError
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind, QuotaScope
from hse_doc_studio.use_cases.chat._support import describe_run_error, run_error_code


@pytest.fixture(autouse=True)
def _restore_language() -> Iterator[None]:
    """Язык интерфейса общий на процесс: не оставляем чужим тестам английский."""
    yield
    set_interface_language(None)


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("ru", "Ваш лимит исчерпан: токены ИИ за сутки, 100 из 100. Сбросится 11.11.2026 00:00 UTC."),
        ("en", "Your limit is used up: AI tokens for the day, 100 of 100. Resets 2026-11-11 00:00 UTC."),
    ],
)
def test__describe_run_error__token_quota_names_numbers_and_reset(lang: str, expected: str) -> None:
    set_interface_language(lang)
    exc = QuotaExceededError(QuotaKind.ai_tokens_day, QuotaScope.user, 100, 100, datetime(2026, 11, 11, tzinfo=UTC))

    assert describe_run_error(exc) == expected
    assert run_error_code(exc) == "quota_exceeded"


def test__describe_run_error__model_and_provider_refusals_have_codes() -> None:
    set_interface_language("ru")

    assert "не разрешена" in describe_run_error(AiModelNotAllowedError("OpenAI", "gpt-x"))
    assert run_error_code(AiModelNotAllowedError("OpenAI", "gpt-x")) == "ai_model_not_allowed"
    assert "временно недоступен" in describe_run_error(AiProviderUnavailableError("OpenAI"))
    assert run_error_code(AiProviderUnavailableError("OpenAI")) == "ai_provider_unavailable"
    assert run_error_code(ValueError("x")) is None


def test__describe_quota_exceeded__storage_is_humanized_in_bytes_units() -> None:
    from hse_doc_studio.core.quotas.messages import describe_quota_exceeded

    set_interface_language("en")
    exc = QuotaExceededError(QuotaKind.storage, QuotaScope.org, 1100 * 1024**2, 1024**3, None)

    assert describe_quota_exceeded(exc) == "Organization limit is used up: storage on the server, 1.1 GB of 1 GB."
