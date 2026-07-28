from __future__ import annotations

from pydantic import BaseModel, Field


class RequirementEntryResponse(BaseModel):
    id: str
    title: str
    source: str
    referenced_in: list[str]
    status: str  # "ok" | "warn" | "err"


class RequirementFormatSchema(BaseModel):
    kind: str  # "macro" | "id" | "custom"
    id_pattern: str | None = None
    definition_docs: list[str] = Field(default_factory=list)
    def_pattern: str | None = None
    ref_pattern: str | None = None


class RequirementsMatrixResponse(BaseModel):
    items: list[RequirementEntryResponse]
    # The format used to build the matrix and whether it is a project override.
    format: RequirementFormatSchema
    format_overridden: bool


class UpdateRequirementsFormatRequest(BaseModel):
    # null → clear the project override and revert to the pack template default.
    format: RequirementFormatSchema | None = None
