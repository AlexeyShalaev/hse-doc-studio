from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.export_import.encryption import decrypt_token
from hse_doc_studio.core.export_import.serialization import (
    persona_from_export_dict,
    provider_from_export_dict,
)
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import (
    IAgentPersonaRepository,
    IAIProviderRepository,
    ISettingsRepository,
)
from hse_doc_studio.use_cases.settings.get_settings import _DEFAULTS

logger = structlog.get_logger()

# Only keys the app knows about are written back, so an old/foreign bundle can't
# inject arbitrary settings (mirrors UpdateSettingsUC's allow-list).
_ALLOWED_SETTING_KEYS = frozenset(_DEFAULTS.keys())
_MERGE_STRATEGIES = frozenset({"skip", "replace"})


@dataclass
class ImportDataInput:
    encrypted: bool
    settings: dict[str, Any] | None = None
    ai_providers: list[dict[str, Any]] = field(default_factory=list)
    agent_personas: list[dict[str, Any]] = field(default_factory=list)
    merge_strategy: str = "skip"  # "skip" keeps existing records, "replace" overwrites by id
    decryption_password: str | None = None


@dataclass
class ImportDataOutput:
    settings_imported: bool = False
    ai_providers_imported: int = 0
    ai_providers_skipped: int = 0
    agent_personas_imported: int = 0
    agent_personas_skipped: int = 0
    errors: list[str] = field(default_factory=list)


class ImportDataUC:
    """Apply an export bundle to local state (app settings + AI providers + custom roles).

    Per-entity failures are collected into ``errors`` instead of aborting the
    whole import, so one malformed record doesn't drop the rest.
    """

    def __init__(
        self,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository,
        agent_persona_repo: IAgentPersonaRepository,
    ) -> None:
        self._settings_repo = settings_repo
        self._ai_provider_repo = ai_provider_repo
        self._agent_persona_repo = agent_persona_repo

    async def execute(self, inp: ImportDataInput) -> ImportDataOutput:  # noqa: C901 — flat per-section import with per-entity error collection
        if inp.encrypted and not inp.decryption_password:
            raise ValueError(
                "The file is encrypted — provide a password to decrypt it"
                if current_interface_language() is Lang.en
                else "Файл зашифрован — укажите пароль для расшифровки"
            )
        if inp.encrypted and inp.decryption_password:
            # Verify the password up front: a wrong one fails the whole import
            # cleanly (nothing written) instead of applying settings and then
            # producing N per-key "decrypt failed" soft errors.
            self._verify_password(inp.ai_providers, inp.decryption_password)
        strategy = inp.merge_strategy if inp.merge_strategy in _MERGE_STRATEGIES else "skip"

        result = ImportDataOutput()

        if inp.settings is not None:
            try:
                self._import_settings(inp.settings)
                result.settings_imported = True
            except Exception as exc:
                result.errors.append(f"settings: {exc}")

        for record in inp.ai_providers:
            try:
                self._import_provider(record, strategy, inp.decryption_password, result)
            except Exception as exc:
                result.errors.append(f"provider {record.get('name', '?')}: {exc}")

        for record in inp.agent_personas:
            try:
                self._import_persona(record, strategy, result)
            except Exception as exc:
                result.errors.append(f"agent_persona {record.get('label', '?')}: {exc}")

        logger.info(
            "settings import finished",
            settings_imported=result.settings_imported,
            providers_imported=result.ai_providers_imported,
            providers_skipped=result.ai_providers_skipped,
            personas_imported=result.agent_personas_imported,
            personas_skipped=result.agent_personas_skipped,
            errors=len(result.errors),
        )
        return result

    def _verify_password(self, records: list[dict[str, Any]], password: str) -> None:
        """Probe the first encrypted api_key so a wrong password fails before any write.

        All keys in a bundle share one password, so a single successful decrypt
        proves it; a single failure means the password is wrong for all of them.
        """
        for record in records:
            api_key = record.get("api_key")
            if not api_key:
                continue
            try:
                decrypt_token(str(api_key), password)
            except ValueError as exc:
                raise ValueError(
                    "Wrong password — could not decrypt the file"
                    if current_interface_language() is Lang.en
                    else "Неверный пароль — не удалось расшифровать файл"
                ) from exc
            return

    def _import_settings(self, imported: dict[str, Any]) -> None:
        current = self._settings_repo.get()
        patch = {k: v for k, v in imported.items() if k in _ALLOWED_SETTING_KEYS}
        self._settings_repo.save({**current, **patch})

    def _import_provider(
        self,
        record: dict[str, Any],
        strategy: str,
        password: str | None,
        result: ImportDataOutput,
    ) -> None:
        record = dict(record)
        if password and record.get("api_key"):
            record["api_key"] = decrypt_token(str(record["api_key"]), password)
        provider = provider_from_export_dict(record)

        if self._ai_provider_repo.get(provider.id) is not None:
            if strategy == "skip":
                result.ai_providers_skipped += 1
                return
            self._ai_provider_repo.update(provider)  # "replace" — overwrite in place, preserving id
        else:
            self._ai_provider_repo.create(provider)
        result.ai_providers_imported += 1

    def _import_persona(self, record: dict[str, Any], strategy: str, result: ImportDataOutput) -> None:
        persona = persona_from_export_dict(record)
        if self._agent_persona_repo.get(persona.id) is not None:
            if strategy == "skip":
                result.agent_personas_skipped += 1
                return
            self._agent_persona_repo.update(persona)
        else:
            self._agent_persona_repo.create(persona)
        result.agent_personas_imported += 1
