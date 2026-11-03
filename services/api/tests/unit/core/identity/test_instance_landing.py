"""Лендинг установки: включён по умолчанию, окружение побеждает правку админа, мусор в БД не выключает его."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.identity.instance_settings import (
    KEY_LANDING_ENABLED,
    InstanceEnvOverrides,
    effective_instance_settings,
)


def test__landing__is_on_by_default() -> None:
    assert effective_instance_settings({}, InstanceEnvOverrides()).landing_enabled is True


def test__landing__stored_value_is_used() -> None:
    assert effective_instance_settings({KEY_LANDING_ENABLED: False}, InstanceEnvOverrides()).landing_enabled is False


@pytest.mark.parametrize("junk", ["false", 0, None, "no"])
def test__landing__non_boolean_stored_value_keeps_the_default(junk: object) -> None:
    assert effective_instance_settings({KEY_LANDING_ENABLED: junk}, InstanceEnvOverrides()).landing_enabled is True


@pytest.mark.parametrize("env_value", [True, False])
def test__landing__env_wins_and_locks_the_key(env_value: bool) -> None:
    env = InstanceEnvOverrides(landing_enabled=env_value)

    assert effective_instance_settings({KEY_LANDING_ENABLED: not env_value}, env).landing_enabled is env_value
    assert KEY_LANDING_ENABLED in env.locked_keys()


def test__landing__unset_env_does_not_lock() -> None:
    assert KEY_LANDING_ENABLED not in InstanceEnvOverrides().locked_keys()
