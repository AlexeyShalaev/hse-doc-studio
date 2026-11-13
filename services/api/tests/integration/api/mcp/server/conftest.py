"""Стенд серверного режима на Postgres берём у тестов личных раннеров: тот же `create_app` и люди с токенами."""

from tests.integration.api.personal.conftest import stand
from tests.integration.api.signing_routes.preset_stand import preset_packs

__all__ = ["preset_packs", "stand"]
