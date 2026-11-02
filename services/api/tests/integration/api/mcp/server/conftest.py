"""Стенд серверного режима на Postgres берём у тестов личных раннеров: тот же `create_app` и люди с токенами."""

from tests.integration.api.personal.conftest import stand

__all__ = ["stand"]
