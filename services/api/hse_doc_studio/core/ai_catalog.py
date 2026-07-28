from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.entities import CatalogModel, HardwareInfo
from hse_doc_studio.core.enums import GpuVendor, Lang

# Curated catalog `tasks` are a small controlled vocabulary stored canonically in
# Russian (api/config.py); translate them to the interface language for display.
_TASK_LABELS: dict[str, dict[Lang, str]] = {
    "черновик": {Lang.ru: "черновик", Lang.en: "draft"},
    "вычитка": {Lang.ru: "вычитка", Lang.en: "proofreading"},
    "переписывание": {Lang.ru: "переписывание", Lang.en: "rewriting"},
    "разбор требований": {Lang.ru: "разбор требований", Lang.en: "requirements analysis"},
    "развёрнутые правки": {Lang.ru: "развёрнутые правки", Lang.en: "detailed edits"},
    "сложные правки": {Lang.ru: "сложные правки", Lang.en: "complex edits"},
    "рассуждения": {Lang.ru: "рассуждения", Lang.en: "reasoning"},
}


def localize_tasks(tasks: list[str], language: Lang) -> list[str]:
    """Map curated `tasks` tokens to the interface language (unknown → as-is)."""
    return [_TASK_LABELS.get(task, {}).get(language, task) for task in tasks]


# Apple Silicon shares one unified memory pool between CPU and GPU; Metal can
# address most of it, but the OS + app still need headroom. Treat this fraction
# of total RAM as the usable "VRAM-equivalent" budget for GPU-accelerated runs.
_APPLE_UNIFIED_GPU_FRACTION = 0.6
# Recommending a model that needs the full RAM budget would thrash the machine;
# keep this much headroom when judging whether a model is *comfortable* enough
# to be the default pick (vs merely runnable).
_COMFORT_HEADROOM_GB = 2.0
# On a CPU-only host large models technically "run" but are painfully slow, so
# we never auto-recommend anything bigger than this as the default.
_CPU_RECOMMEND_MAX_PARAMS_B = 4.0


@dataclass(frozen=True)
class ModelCatalog:
    # Thin domain holder so the curated list can be injected by a single,
    # unambiguous type (rather than a bare ``list[CatalogModel]`` DI key).
    models: list[CatalogModel]


@dataclass(frozen=True)
class ModelFit:
    # A catalog model paired with how it fits the detected hardware.
    model: CatalogModel
    runnable: bool  # fits at all (on GPU or on CPU)
    on_gpu: bool  # fits within the detected GPU/VRAM budget
    recommended: bool  # the single best default for this hardware
    note: str  # short RU explanation shown next to the model


def _gpu_budget_gb(hw: HardwareInfo) -> float | None:
    """Usable accelerator memory budget in GB, or None when there is no GPU."""
    if hw.gpu_vendor == GpuVendor.nvidia and hw.vram_mb:
        return hw.vram_mb / 1024.0
    if hw.gpu_vendor == GpuVendor.apple and hw.total_ram_mb:
        # No dedicated VRAM — Metal draws from the unified pool.
        return (hw.total_ram_mb / 1024.0) * _APPLE_UNIFIED_GPU_FRACTION
    return None


def _cpu_budget_gb(hw: HardwareInfo) -> float | None:
    return hw.total_ram_mb / 1024.0 if hw.total_ram_mb else None


def recommend(catalog: ModelCatalog, hw: HardwareInfo, language: Lang = Lang.ru) -> list[ModelFit]:
    """Annotate each catalog model with how it fits `hw` and pick one default.

    Pure function (no IO) so it is exhaustively unit-testable — the interface
    language is passed in (it only affects the human-readable `note`). The single
    `recommended` model is the largest one that fits comfortably — preferring
    GPU placement, and on CPU-only hosts capped to a small size so we never
    nudge a user toward an unbearably slow default.
    """
    gpu_gb = _gpu_budget_gb(hw)
    cpu_gb = _cpu_budget_gb(hw)

    fits: list[ModelFit] = []
    for model in catalog.models:
        on_gpu = gpu_gb is not None and model.min_vram_gb <= gpu_gb
        on_cpu = cpu_gb is not None and model.min_ram_gb <= cpu_gb
        fits.append(
            ModelFit(
                model=model,
                runnable=on_gpu or on_cpu,
                on_gpu=on_gpu,
                recommended=False,
                note=_fit_note(model, hw, gpu_gb, cpu_gb, on_gpu=on_gpu, on_cpu=on_cpu, language=language),
            )
        )

    best = _pick_default(fits, gpu_gb, cpu_gb)
    if best is None:
        return fits
    return [
        ModelFit(
            model=f.model,
            runnable=f.runnable,
            on_gpu=f.on_gpu,
            recommended=f.model.name == best.model.name,
            note=f.note,
        )
        for f in fits
    ]


def _pick_default(fits: list[ModelFit], gpu_gb: float | None, cpu_gb: float | None) -> ModelFit | None:
    # Prefer the largest model that fits comfortably on the GPU.
    if gpu_gb is not None:
        gpu_ok = [f for f in fits if f.on_gpu and f.model.min_vram_gb + _COMFORT_HEADROOM_GB <= gpu_gb] or [
            f for f in fits if f.on_gpu
        ]
        if gpu_ok:
            return max(gpu_ok, key=lambda f: f.model.params_b)
    # CPU-only: cap the default to a small, bearable size.
    if cpu_gb is not None:
        cpu_ok = [
            f
            for f in fits
            if f.runnable
            and f.model.params_b <= _CPU_RECOMMEND_MAX_PARAMS_B
            and f.model.min_ram_gb + _COMFORT_HEADROOM_GB <= cpu_gb
        ]
        if cpu_ok:
            return max(cpu_ok, key=lambda f: f.model.params_b)
    return None


def _fit_note(
    model: CatalogModel,
    hw: HardwareInfo,
    gpu_gb: float | None,
    cpu_gb: float | None,
    *,
    on_gpu: bool,
    on_cpu: bool,
    language: Lang = Lang.ru,
) -> str:
    en = language == Lang.en
    if on_gpu and gpu_gb is not None:
        if en:
            where = "VRAM" if hw.gpu_vendor == GpuVendor.nvidia else "GPU memory"
            return f"Fits in {where} (~{gpu_gb:.0f} GB), fast response"
        where = "видеопамять" if hw.gpu_vendor == GpuVendor.nvidia else "память GPU"
        return f"Поместится в {where} (~{gpu_gb:.0f} ГБ), быстрый отклик"
    if on_cpu:
        return (
            "Runs on CPU — works, but slower than on a GPU"
            if en
            else "Пойдёт на CPU — работает, но медленнее, чем на GPU"
        )
    if cpu_gb is not None:
        return (
            f"Not enough memory: needs ~{model.min_ram_gb:.0f} GB RAM"
            if en
            else f"Недостаточно памяти: нужно ~{model.min_ram_gb:.0f} ГБ ОЗУ"
        )
    return (
        "Could not estimate resources — install at your own risk"
        if en
        else "Не удалось оценить ресурсы — установка на свой риск"
    )
