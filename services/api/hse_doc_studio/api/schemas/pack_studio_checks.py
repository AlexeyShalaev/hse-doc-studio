"""Схемы `/api/v1/pack-studio/.../checks`: файлы правил и `checks_version` формой (срез T14).

Эталоны лежат в `contracts/pack-studio/fixtures`, тест `tests/unit/contract/test_pack_studio_contract.py` сверяет их
с этими моделями.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.pack_studio import ReadOnlyReason

RuleSeverityName = Literal["info", "warn", "err"]
OverrideSeverityName = Literal["info", "warn", "err", "skipped"]
ChecksOpName = Literal["set_header", "add_rule", "set_rule", "remove_rule", "move_rule"]
Localized = dict[str, str]


class PackChecksHeader(StrictModel):
    label: Localized = Field(max_length=4)
    ref: Localized = Field(max_length=4)
    # Текст источника по языкам; ссылка отдельно.
    source: Localized = Field(default_factory=dict, max_length=4)
    url: str | None = Field(default=None, max_length=1000)


class PackCheckRule(StrictModel):
    """Правило: `applies_to` null значит «все документы» (`*`); `params` как в YAML."""

    id: str = Field(min_length=1, max_length=160)
    title: Localized = Field(max_length=4)
    description: Localized = Field(default_factory=dict, max_length=4)
    category: str | None = Field(default=None, max_length=64)
    applies_to: list[str] | None = Field(default=None, max_length=64)
    default_severity: RuleSeverityName
    engine: str = Field(min_length=1, max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)


class PackIndexedRule(StrictModel):
    index: int
    entry: PackCheckRule | None
    # Параметры правила текстом YAML (для правки движков без своих полей); null у битого правила.
    params_yaml: str | None
    error: str | None


class PackChecksFile(StrictModel):
    path: str
    # Имя файла в `checks/`; без `.yaml` это префикс id правил.
    name: str
    etag: str
    read_only: ReadOnlyReason | None
    header: PackChecksHeader
    rules: list[PackIndexedRule]
    # Первая проблема разбора файла: правило, которое лоадер выбросит, повтор id, шапка без названия.
    error: str | None


class PackChecksConfig(StrictModel):
    """`checks_version` из `version.yaml` с ETag манифеста."""

    path: str
    etag: str
    read_only: ReadOnlyReason | None
    disabled_categories: list[str]
    disabled: list[str]
    severity_override: dict[str, str]


class PackChecksResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    documents: list[str]
    files: list[PackChecksFile]
    config: PackChecksConfig
    # Движки проверок и структурные проверки, у которых в форме свои поля.
    engines: list[str]
    structural_checks: list[str]


class PackChecksOp(StrictModel):
    op: ChecksOpName
    header: PackChecksHeader | None = None
    index: int | None = Field(default=None, ge=0, le=1000)
    to: int | None = Field(default=None, ge=0, le=1000)
    rule: PackCheckRule | None = None
    # Параметры правила текстом YAML (движки без своих полей); заменяет `rule.params`.
    params_yaml: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def _fields(self) -> PackChecksOp:
        if self.op == "set_header" and self.header is None:
            raise ValueError("set_header needs header")
        if self.op in {"add_rule", "set_rule"} and self.rule is None:
            raise ValueError(f"{self.op} needs rule")
        if self.op in {"set_rule", "remove_rule", "move_rule"} and self.index is None:
            raise ValueError(f"{self.op} needs index")
        if self.op == "move_rule" and self.to is None:
            raise ValueError("move_rule needs to")
        return self


class PackChecksPatchRequest(StrictModel):
    ops: list[PackChecksOp] = Field(min_length=1, max_length=50)


class PackChecksConfigRequest(StrictModel):
    disabled_categories: list[str] = Field(default_factory=list, max_length=64)
    disabled: list[str] = Field(default_factory=list, max_length=500)
    severity_override: dict[str, OverrideSeverityName] = Field(default_factory=dict, max_length=500)
