from __future__ import annotations

from pydantic import BaseModel, Field


class ArtifactsConfig(BaseModel):
    """Только серверный режим: PDF, выгруженные локальной Студией после её сборки (docs/design/local-sync.md, P4)."""

    max_pdf_bytes: int = Field(
        default=104_857_600,
        ge=1_048_576,
        description="Предел размера одного PDF, выгружаемого локальной Студией, в байтах.",
    )
    keep_per_document: int = Field(
        default=5, ge=1, le=50, description="Сколько последних выгруженных PDF хранится на документ."
    )
