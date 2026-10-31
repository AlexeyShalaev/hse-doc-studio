"""Артефакт проекта -> тело ответа API."""

from __future__ import annotations

from hse_doc_studio.api.schemas.artifacts import ProjectArtifactResponse
from hse_doc_studio.core.artifacts.entities import ProjectArtifact


def map_artifact(artifact: ProjectArtifact) -> ProjectArtifactResponse:
    return ProjectArtifactResponse(
        id=str(artifact.id),
        kind=artifact.kind.value,
        doc_id=artifact.doc_id,
        file_name=artifact.file_name,
        size=artifact.size,
        sha256=artifact.sha256,
        pages=artifact.pages,
        source_commit=artifact.source_commit,
        built_at=artifact.built_at,
        uploaded_at=artifact.uploaded_at,
        uploaded_by_name=artifact.uploaded_by_name,
        client_name=artifact.client_name,
        file_url=f"/api/v1/projects/{artifact.project_id}/artifacts/{artifact.id}/file",
    )
