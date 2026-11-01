"""Перенос данных пользователя из каталога локальной Студии в его аккаунт на сервере.

Идемпотентность по записи: ИИ-провайдер с тем же id и настройка, уже заданная на сервере, не трогаются,
поэтому повторный запуск ничего не дублирует и не затирает то, что человек успел изменить на сервере.
Dry-run проходит те же проверки, но в хранилище не пишет.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.export_import.local_data import ILocalDataReader
from hse_doc_studio.core.repositories import IAIProviderRepository, ISettingsRepository
from hse_doc_studio.core.settings_scope import SETTING_SCOPES, SettingScope
from hse_doc_studio.use_cases.ai_providers.base_url import authorize_base_url
from hse_doc_studio.use_cases.settings.get_settings import _DEFAULTS, MACHINE_LOCAL_SETTING_KEYS
from hse_doc_studio.use_cases.settings.value_rules import SETTING_VALUE_RULES

logger = structlog.get_logger()

_TRANSFERABLE_KEYS = frozenset(_DEFAULTS.keys()) - MACHINE_LOCAL_SETTING_KEYS


class ImportNoteCode(StrEnum):
    unreadable = "unreadable"
    invalid_setting = "invalid_setting"
    instance_setting_skipped = "instance_setting_skipped"
    provider_failed = "provider_failed"
    not_transferred = "not_transferred"


@dataclass(frozen=True)
class ImportNote:
    code: ImportNoteCode
    subject: str = ""
    detail: str = ""


@dataclass
class ImportUserDataInput:
    data_dir: Path
    dry_run: bool = False
    include_instance: bool = False


@dataclass
class ImportUserDataReport:
    dry_run: bool
    settings_created: int = 0
    settings_kept: int = 0
    providers_created: int = 0
    providers_kept: int = 0
    notes: list[ImportNote] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(n.code is ImportNoteCode.provider_failed for n in self.notes)


class ImportUserDataUC:
    """Работает от имени пользователя из текущего актора: он же владелец записей, которые появятся."""

    def __init__(
        self,
        reader: ILocalDataReader,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository,
        egress: IEgressPolicy | None = None,
    ) -> None:
        self._reader = reader
        self._settings = settings_repo
        self._providers = ai_provider_repo
        self._egress = egress

    async def execute(self, inp: ImportUserDataInput) -> ImportUserDataReport:
        data = self._reader.read(inp.data_dir)
        report = ImportUserDataReport(dry_run=inp.dry_run)
        report.notes.extend(ImportNote(ImportNoteCode.unreadable, name) for name in data.unreadable)
        await self._import_settings(data.settings, inp, report)
        await self._import_providers(data.ai_providers, inp, report)
        report.notes.extend(ImportNote(ImportNoteCode.not_transferred, kind.value) for kind in data.not_transferred)
        logger.info(
            "user data import finished",
            dry_run=inp.dry_run,
            settings_created=report.settings_created,
            providers_created=report.providers_created,
            notes=len(report.notes),
        )
        return report

    async def _import_settings(
        self, local: dict[str, Any], inp: ImportUserDataInput, report: ImportUserDataReport
    ) -> None:
        current = await self._settings.get()
        fresh: dict[str, Any] = {}
        for key, value in sorted(local.items()):
            if key not in _TRANSFERABLE_KEYS:
                continue
            if SETTING_SCOPES.get(key) is SettingScope.instance and not inp.include_instance:
                report.notes.append(ImportNote(ImportNoteCode.instance_setting_skipped, key))
                continue
            rule = SETTING_VALUE_RULES.get(key)
            checked = value if rule is None else rule(value)
            if checked is None:
                report.notes.append(ImportNote(ImportNoteCode.invalid_setting, key))
                continue
            if key in current:
                report.settings_kept += 1
            else:
                fresh[key] = checked
        report.settings_created = len(fresh)
        if fresh and not inp.dry_run:
            await self._settings.save({**current, **fresh})

    async def _import_providers(self, providers: Any, inp: ImportUserDataInput, report: ImportUserDataReport) -> None:
        for provider in providers:
            # Рантайм Ollama поднимается на самой машине заново, его адрес чужому хосту ничего не говорит.
            if provider.type is AIProviderType.ollama:
                continue
            if await self._providers.get(provider.id) is not None:
                report.providers_kept += 1
                continue
            try:
                await authorize_base_url(self._egress, provider.base_url, provider.owner_kind)
                if not inp.dry_run:
                    await self._providers.create(provider)
            except Exception as exc:  # noqa: BLE001 — одна запись не должна ронять остальные
                report.notes.append(ImportNote(ImportNoteCode.provider_failed, provider.name, str(exc)[:200]))
                continue
            report.providers_created += 1
