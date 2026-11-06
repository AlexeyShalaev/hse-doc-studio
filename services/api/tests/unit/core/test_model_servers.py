"""Оценка требований и сборка контейнера: чистые правила серверов моделей."""

from __future__ import annotations

from hse_doc_studio.core.model_servers import (
    Engine,
    Fit,
    HostResources,
    build_container_spec,
    catalog_for,
    estimate_requirements,
    guess_params_b,
    valid_model_ref,
)

from tests.fakes.model_servers import hardware

DISK = HostResources("x86_64", 500_000)


def test_params_from_catalog_and_name() -> None:
    assert guess_params_b("qwen3:8b") == 8.0
    assert guess_params_b("org/Some-Model-70B-Instruct") == 70.0
    assert guess_params_b("org/tiny-500m") == 0.5
    assert guess_params_b("org/no-size") is None


def test_small_model_fits_ram() -> None:
    est = estimate_requirements(Engine.ollama, "qwen3:4b", hardware(ram_mb=16384), DISK)
    assert est.fit is Fit.fits
    assert est.memory_kind == "ram"
    assert est.disk_ok is True


def test_big_model_too_large_for_gpu() -> None:
    est = estimate_requirements(Engine.vllm, "org/model-70b", hardware(nvidia=True, vram_mb=24576), DISK)
    assert est.fit is Fit.too_large
    assert est.memory_kind == "vram"
    assert "memory_low" in est.reasons


def test_vllm_without_gpu_has_reason() -> None:
    est = estimate_requirements(Engine.vllm, "Qwen/Qwen3-4B", hardware(), DISK)
    assert "engine_requires_gpu" in est.reasons
    assert "cpu_only" in est.reasons


def test_unknown_size_does_not_block() -> None:
    est = estimate_requirements(Engine.ollama, "mystery", hardware(), DISK)
    assert est.fit is Fit.unknown
    assert "size_unknown" in est.reasons


def test_low_disk_is_reported() -> None:
    est = estimate_requirements(Engine.ollama, "qwen3:32b", hardware(ram_mb=65536), HostResources("x86_64", 1000))
    assert est.disk_ok is False
    assert "disk_low" in est.reasons


def test_model_ref_validation() -> None:
    assert valid_model_ref("Qwen/Qwen3-8B")
    assert valid_model_ref("llama3.1:8b")
    assert not valid_model_ref("../etc/passwd")
    assert not valid_model_ref("a b; rm -rf /")
    assert not valid_model_ref("--flag")


def test_catalog_filters_by_engine_and_query() -> None:
    assert all(Engine.ollama in m.engines for m in catalog_for(Engine.ollama))
    assert [m.ref for m in catalog_for(Engine.vllm, "gemma")] == ["google/gemma-3-12b-it"]


def test_vllm_spec_keeps_key_out_of_arguments() -> None:
    spec = build_container_spec(
        Engine.vllm, server_id="ab12", model="Qwen/Qwen3-4B", api_key="K3Y", hf_token="HFT", gpu=True
    )
    assert "K3Y" not in " ".join(spec.command)
    assert spec.secret_env == {"HF_TOKEN": "HFT", "VLLM_API_KEY": "K3Y"}
    assert spec.gpu
    assert not spec.gpu_optional
    assert spec.name == "hse-ms-ab12"


def test_sglang_spec_expands_key_from_env_inside_container() -> None:
    spec = build_container_spec(Engine.sglang, server_id="ab12", model="Qwen/Qwen3-4B", api_key="K3Y")
    assert spec.command[:2] == ("sh", "-c")
    assert "K3Y" not in spec.command[2]
    assert '--api-key "$SGLANG_API_KEY"' in spec.command[2]
    assert spec.secret_env == {"SGLANG_API_KEY": "K3Y"}


def test_sglang_model_name_is_quoted() -> None:
    spec = build_container_spec(Engine.sglang, server_id="ab12", model="org/model;x")
    assert "'org/model;x'" in spec.command[2]


def test_ollama_spec_is_gpu_optional() -> None:
    spec = build_container_spec(Engine.ollama, server_id="ab12", model="qwen3:4b", gpu=True)
    assert spec.gpu_optional
    assert spec.command == ()
