"""Совместная правка в реальном времени (Yjs) и пределы нагрузки на неё."""

from pydantic import BaseModel, Field


class CollabConfig(BaseModel):
    """HSE_STUDIO__COLLAB__*. Работает только на сервере; документ закреплён за одной репликой api."""

    enabled: bool = Field(default=True, description="Включить совместную правку; выключена, редактор сохраняет сам.")
    max_clients_per_room: int = Field(default=16, ge=1, description="Одновременных подключений к одному файлу.")
    max_rooms_per_project: int = Field(default=8, ge=1, description="Файлов проекта, открытых для совместной правки.")
    max_rooms_total: int = Field(default=200, ge=1, description="Открытых файлов на реплику api.")
    max_connections_per_user: int = Field(default=8, ge=1, description="Подключений одного человека (вкладки).")
    max_message_bytes: int = Field(default=1_048_576, ge=1024, description="Размер одного сообщения от клиента.")
    max_doc_bytes: int = Field(default=2_097_152, ge=1024, description="Размер текста, который открывается в комнате.")
    persist_delay_s: float = Field(default=0.8, gt=0, description="Пауза после правки до записи на диск.")
    persist_max_wait_s: float = Field(
        default=5.0, gt=0, description="Самое долгое ожидание записи при непрерывном вводе."
    )
    poll_interval_s: float = Field(
        default=1.0, gt=0, description="Как часто комната сверяет файл с диском (git, агент)."
    )
    idle_ttl_s: float = Field(default=20.0, ge=0, description="Сколько жить комнате после выхода последнего участника.")
    awareness_per_second: int = Field(default=30, ge=1, description="Обновлений курсора в секунду от одного клиента.")
    recheck_s: float = Field(default=20.0, gt=0, description="Как часто пересматриваются права открытого подключения.")
    outbox_size: int = Field(
        default=512, ge=8, description="Очередь исходящих сообщений клиента, дальше он отключается."
    )
