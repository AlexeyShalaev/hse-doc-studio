"""Ограничение частоты запросов: порт и каталог правил.

Счётчики живут в памяти одного процесса (реплика api одна, см. helm Recreate), поэтому при перезапуске окна
обнуляются. Долгая защита от подбора пароля устроена иначе: прогрессивная задержка хранится в БД
(`login_attempts`, `core.identity.session_policy.login_delay`) и перезапуск её не сбрасывает.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateRule:
    """Не более `limit` запросов на ключ за скользящее окно `window_s` секунд."""

    name: str
    limit: int
    window_s: float


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    # Через сколько секунд окно освободит место (целое, не меньше 1); при allowed всегда 0.
    retry_after_s: int = 0
    remaining: int = 0


class IRateLimiter(Protocol):
    async def hit(self, rule: RateRule, key: str) -> RateDecision:
        """Учитывает запрос; отказанный запрос в окно не записывается, иначе клиент сам продлевал бы блокировку."""
        ...


# Каталог: вход и регистрация считаются по IP, письма по e-mail, дорогие операции по пользователю.
AUTH_IP = RateRule("auth_ip", limit=30, window_s=60)
AUTH_EMAIL = RateRule("auth_email", limit=5, window_s=3600)
COMPILE = RateRule("compile", limit=20, window_s=60)
UPLOAD = RateRule("upload", limit=120, window_s=60)
AGENT = RateRule("agent", limit=30, window_s=60)
GIT_SYNC = RateRule("git_sync", limit=20, window_s=60)
# Поиск кода сопряжения раннера на сайте: и неверные коды тоже считаются (по человеку и по IP).
RUNNER_PAIRING = RateRule("runner_pairing", limit=10, window_s=60)

RULES: dict[str, RateRule] = {
    rule.name: rule for rule in (AUTH_IP, AUTH_EMAIL, COMPILE, UPLOAD, AGENT, GIT_SYNC, RUNNER_PAIRING)
}
