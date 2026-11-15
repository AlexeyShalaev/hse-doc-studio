"""Каталоги паков (docs/design/template-studio.md, 10.3, срез T17): пределы ревизии источника и отслеживание."""

from pydantic import BaseModel, Field


class PackCatalogConfig(BaseModel):
    """HSE_STUDIO__PACK_CATALOG__*. Пределы защищают диск и память api от чужого источника паков (раздел 9)."""

    max_archive_bytes: int = Field(
        default=104_857_600,
        ge=1024,
        description="Largest uploaded packs archive, and largest git object store fetched for one source revision.",
    )
    max_files: int = Field(default=20_000, ge=10, description="Most files in one source revision of packs.")
    max_bytes: int = Field(
        default=536_870_912, ge=1_048_576, description="Largest total size of the files in one source revision."
    )
    inspect_timeout_s: float = Field(
        default=120.0, gt=0, description="Time limit of the isolated process that reads and lints a source revision."
    )
    inspect_memory_bytes: int = Field(
        default=1_073_741_824, ge=67_108_864, description="Memory limit of that isolated process (Linux)."
    )
    reload_check_s: float = Field(
        default=2.0,
        ge=0,
        description="How often an api process looks for a new packs catalog revision applied by another process.",
    )
    track_tick_s: float = Field(
        default=3600.0,
        gt=0,
        description="Tick of daily tracking: tracked git sources older than a day are checked and applied.",
    )
