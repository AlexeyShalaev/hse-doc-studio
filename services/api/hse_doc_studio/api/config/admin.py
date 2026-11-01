"""Админка установки."""

from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from hse_doc_studio.core.identity.admin_access import AdminAccessPolicy


class AdminConfig(BaseModel):
    """Ограничения админки (HSE_STUDIO__ADMIN__*): в `/admin` и `/api/admin` пускают только с этих хоста и адресов."""

    allowed_hosts: list[str] = Field(
        default_factory=list,
        description=(
            "Имена, под которыми открывается админка (заголовок Host): admin.example.org, *.example.org. "
            "Пусто: без ограничения."
        ),
    )
    allowed_cidrs: list[str] = Field(
        default_factory=list,
        description=(
            "IP и CIDR клиентов, которым открыта админка (адрес по auth.trusted_proxies). Пусто: без ограничения. "
            "Заданы оба списка: нужно пройти оба."
        ),
    )

    @field_validator("allowed_hosts", "allowed_cidrs")
    @classmethod
    def _strip_blank(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def _valid_entries(self) -> Self:
        AdminAccessPolicy.parse(self.allowed_hosts, self.allowed_cidrs)
        return self

    @property
    def policy(self) -> AdminAccessPolicy:
        return AdminAccessPolicy.parse(self.allowed_hosts, self.allowed_cidrs)
