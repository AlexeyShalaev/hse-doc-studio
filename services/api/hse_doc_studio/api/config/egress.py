"""Исходящие запросы по адресам пользователей."""

from pydantic import BaseModel, Field, field_validator

from hse_doc_studio.core.egress import EgressAllowlist


class EgressConfig(BaseModel):
    """SSRF-защита общего сервера (HSE_STUDIO__EGRESS__*). В режиме local не применяется."""

    allowlist: list[str] = Field(
        default_factory=list,
        description=(
            "Внутренние узлы, к которым пользователям можно ходить: имя (git.corp.local, *.corp.local), "
            "IP или CIDR. Адреса метаданных облака и link-local закрыты всегда."
        ),
    )

    @field_validator("allowlist")
    @classmethod
    def _valid_entries(cls, value: list[str]) -> list[str]:
        EgressAllowlist.parse(value)
        return value
