"""Автообновление сервера (HSE_STUDIO__SERVER_UPDATE__*). Политика, окно и бэкап правятся в админке."""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class ServerUpdateConfig(BaseModel):
    enabled: bool = Field(default=True, description="Включает проверку релизов, планировщик и раздел админки.")
    executor: Literal["compose", "none"] = Field(
        default="none",
        description="Кто ставит обновление. compose: сервис-апдейтер рядом с api (docker compose). "
        "none: только проверка и уведомления, ставит оператор (helm upgrade --atomic, свой CI).",
    )
    updater_token: SecretStr = Field(
        default=SecretStr(""),
        description="Общий секрет апдейтера (Bearer). Пусто: протокол апдейтера выключен и запуски не выдаются.",
    )
    tick_s: float = Field(default=60.0, ge=5, le=3600, description="Период планировщика обновлений.")
    check_interval_s: float = Field(default=6 * 3600.0, ge=300, description="Как часто спрашивать фид релизов.")
    updater_stale_s: float = Field(default=90.0, ge=15, description="Сколько апдейтер может молчать и считаться живым.")
    run_lost_s: float = Field(
        default=900.0, ge=120, description="Сколько апдейтер молчит посреди запуска, прежде чем запуск потерян."
    )
