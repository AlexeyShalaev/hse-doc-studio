from __future__ import annotations

import pytest
from hse_doc_studio.api.config import JobsConfig
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry

from tests.unit.infra.jobs.dispatcher_helpers import FakeOfficeHandler


def test__handler_registry__registered_handler__returned_by_kind() -> None:
    registry = JobHandlerRegistry()
    handler = FakeOfficeHandler()

    registry.register(JobKind.office_convert, handler)

    assert registry.get(JobKind.office_convert) is handler


def test__handler_registry__unknown_kind__value_error() -> None:
    with pytest.raises(ValueError, match="no handler registered for job kind compile"):
        JobHandlerRegistry().get(JobKind.compile)


def test__handler_registry__registered_twice__value_error() -> None:
    registry = JobHandlerRegistry()
    registry.register(JobKind.office_convert, FakeOfficeHandler())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(JobKind.office_convert, FakeOfficeHandler())


def test__jobs_config__round_trip_is_off_by_default() -> None:
    assert JobsConfig().round_trip_payloads is False
