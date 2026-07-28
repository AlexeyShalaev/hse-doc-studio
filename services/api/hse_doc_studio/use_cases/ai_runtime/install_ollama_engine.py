from __future__ import annotations

from collections.abc import AsyncGenerator

from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager


class InstallOllamaEngineUC:
    """Stream `docker pull ollama/ollama` so the UI can show download progress.

    Pinned to the single configured engine image (never a user-supplied tag),
    so this cannot be used to pull arbitrary images. Reuses the shared
    `DockerImageManager.pull` stream (same SSE shape as the LanguageTool /
    compile installs).
    """

    def __init__(self, image_manager: DockerImageManager, image: str) -> None:
        self._image_manager = image_manager
        self._image = image

    async def execute(self) -> AsyncGenerator[str, None]:
        return await self._image_manager.pull(self._image)
