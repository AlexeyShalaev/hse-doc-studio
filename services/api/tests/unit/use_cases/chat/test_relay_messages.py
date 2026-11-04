"""Понятные причины сбоя модели за раннером и переполнения окна Ollama (часть 1 дизайн-заметки)."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.use_cases.ai_relay.client import AiRelayError
from hse_doc_studio.use_cases.chat._support import MODEL_CONTEXT_EXCEEDED, describe_run_error, run_error_code

OVERFLOW = "Error code: 400 - request (4760 tokens) exceeds the available context size (4096 tokens), try increasing it"


class BadRequestError(Exception):
    pass


def relay(code: RelayErrorCode) -> AiRelayError:
    return AiRelayError(code, runner_name="MacBook Анны")


@pytest.mark.parametrize(
    ("code", "needle"),
    [
        (RelayErrorCode.upstream_unreachable, "модель на его компьютере не отвечает"),
        (RelayErrorCode.upstream_timeout, "не ответила вовремя"),
        (RelayErrorCode.runner_offline, "не в сети"),
        (RelayErrorCode.runner_paused, "на паузе"),
        (RelayErrorCode.runner_revoked, "отозван"),
        (RelayErrorCode.endpoint_missing, "больше не открывает эту модель"),
        (RelayErrorCode.relay_unavailable, "не ответил"),
    ],
)
def test__describe_run_error__relay_failure_names_the_runner_and_the_reason(code: RelayErrorCode, needle: str) -> None:
    text = describe_run_error(relay(code))

    assert "MacBook Анны" in text
    assert needle in text


def test__describe_run_error__model_down_behind_a_live_runner_says_start_ollama() -> None:
    assert "Запустите Ollama" in describe_run_error(relay(RelayErrorCode.upstream_unreachable))


def test__describe_run_error__ollama_context_overflow_is_explained_with_numbers_and_a_fix() -> None:
    exc = BadRequestError(OVERFLOW)

    text = describe_run_error(exc)

    assert "4760" in text
    assert "4096" in text
    assert "num_ctx" in text
    assert "BadRequestError" not in text
    assert run_error_code(exc) == MODEL_CONTEXT_EXCEEDED


def test__describe_run_error__other_errors_keep_the_old_form() -> None:
    assert describe_run_error(BadRequestError("bad thing")) == "BadRequestError: bad thing"
    assert run_error_code(BadRequestError("bad thing")) is None
