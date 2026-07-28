from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.export_import.encryption import encrypt_token
from hse_doc_studio.core.export_import.serialization import persona_to_export_dict, provider_to_export_dict
from hse_doc_studio.core.repositories import (
    IAgentPersonaRepository,
    IAIProviderRepository,
    ISettingsRepository,
)
from hse_doc_studio.core.system_capacity import ISystemCapacityProbe
from hse_doc_studio.use_cases.settings.get_settings import GetSettingsUC

# Bumped only on a breaking change to the bundle shape; import tolerates any value.
EXPORT_FORMAT_VERSION = "1.0"


@dataclass
class ExportDataInput:
    include_settings: bool = True
    include_ai_providers: bool = True
    include_agent_personas: bool = True
    # When set, provider api_keys are encrypted (PBKDF2 + Fernet) under this password.
    encryption_password: str | None = None


@dataclass
class ExportDataOutput:
    version: str
    exported_at: datetime
    encrypted: bool
    settings: dict[str, Any] | None
    ai_providers: list[dict[str, Any]] = field(default_factory=list)
    agent_personas: list[dict[str, Any]] = field(default_factory=list)


class ExportDataUC:
    """Bundle local app settings + configured AI providers into one portable file.

    Provider secrets (``api_key``) are written either in plaintext or — when an
    encryption password is supplied — encrypted per-field. The auto-managed
    ``ollama`` provider is never exported: it is rebuilt from the local runtime
    on the target machine and its base_url is host-specific.
    """

    def __init__(
        self,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository,
        agent_persona_repo: IAgentPersonaRepository,
        capacity_probe: ISystemCapacityProbe | None = None,
    ) -> None:
        self._settings_repo = settings_repo
        self._ai_provider_repo = ai_provider_repo
        self._agent_persona_repo = agent_persona_repo
        # Выгружаем ровно то, что пользователь видит в Настройках, — включая
        # дефолты, посчитанные по этой машине.
        self._get_settings = GetSettingsUC(settings_repo, capacity_probe)

    async def execute(self, inp: ExportDataInput) -> ExportDataOutput:
        password = inp.encryption_password or None

        settings: dict[str, Any] | None = None
        if inp.include_settings:
            settings = (await self._get_settings.execute()).settings

        providers: list[dict[str, Any]] = []
        encrypted_any = False
        if inp.include_ai_providers:
            for provider in self._ai_provider_repo.list_all():
                if provider.type == AIProviderType.ollama:
                    continue  # auto-managed; recreated from the local runtime, not portable
                record = provider_to_export_dict(provider)
                if password and record["api_key"]:
                    record["api_key"] = encrypt_token(record["api_key"], password)
                    encrypted_any = True
                providers.append(record)

        # Custom agent roles carry no secrets — exported in plaintext regardless.
        personas: list[dict[str, Any]] = []
        if inp.include_agent_personas:
            personas = [persona_to_export_dict(p) for p in self._agent_persona_repo.list_all()]

        return ExportDataOutput(
            version=EXPORT_FORMAT_VERSION,
            exported_at=datetime.now(timezone.utc),
            # "encrypted" reflects whether a secret was ACTUALLY encrypted — not just
            # that a password was supplied. A password with nothing to encrypt (no
            # provider keys) must not produce an "encrypted" bundle, or import would
            # accept any password (there is nothing to verify it against).
            encrypted=encrypted_any,
            settings=settings,
            ai_providers=providers,
            agent_personas=personas,
        )
