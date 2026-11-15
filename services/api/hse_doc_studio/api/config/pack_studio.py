"""Студия шаблонов (docs/design/template-studio.md, раздел 3): включение раздела и пределы рабочих пространств."""

from pydantic import BaseModel, Field


class PackStudioConfig(BaseModel):
    """HSE_STUDIO__PACK_STUDIO__*. Пределы защищают диск и память api от чужого репозитория паков (раздел 9)."""

    enabled: bool | None = Field(
        default=None,
        description=(
            "Force the section on or off. Unset: locally the Settings toggle decides, on a server the instance admin."
        ),
    )
    standalone: bool = Field(
        default=False, description="Pack Studio profile: the start page is /pack-studio (deploy/pack-studio)."
    )
    max_workspaces_per_user: int = Field(default=10, ge=1, description="Workspaces one person may keep.")
    max_file_bytes: int = Field(
        default=2_097_152, ge=1024, description="Largest file written through the Pack Studio (as pre-commit)."
    )
    max_read_bytes: int = Field(
        default=26_214_400, ge=1024, description="Largest file of a workspace the Pack Studio reads into memory."
    )
    max_clone_bytes: int = Field(
        default=1_073_741_824,
        ge=1_048_576,
        description="Largest object store of a cloned packs repository (partial clone: commits and trees).",
    )
    max_tree_bytes: int = Field(
        default=268_435_456, ge=1_048_576, description="Largest total size of the files under the packs folder."
    )
    max_tree_files: int = Field(default=20_000, ge=10, description="Most files under the packs folder.")
    default_packs_path: str = Field(default="packs", description="Packs folder inside a repository by default.")
    # Предпросмотр (template-studio.md, раздел 6, срез T7)
    preview_max_concurrent: int = Field(default=2, ge=1, description="Running preview builds one person may have.")
    preview_describe_timeout_s: float = Field(
        default=20.0, gt=0, description="Time limit of the isolated process that reads a draft version."
    )
    preview_render_timeout_s: float = Field(
        default=30.0, gt=0, description="Time limit of the isolated process that renders the synthetic project."
    )
    preview_render_memory_bytes: int = Field(
        default=536_870_912, ge=67_108_864, description="Memory limit of the isolated render process (Linux)."
    )
    preview_cache_entries: int = Field(default=200, ge=1, description="Built preview PDFs kept by cache key.")
    preview_keep_hours: float = Field(
        default=24.0, gt=0, description="How long preview build records, logs and leftover folders are kept."
    )
    hosting_timeout_s: float = Field(
        default=20.0, gt=0, description="Timeout for one request to the git hosting API (pull request, CI status)."
    )
    max_diff_bytes: int = Field(
        default=1_048_576, ge=1024, description="Largest diff of a workspace against its base branch shown at once."
    )
