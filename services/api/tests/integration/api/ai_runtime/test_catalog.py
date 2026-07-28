from __future__ import annotations

from httpx import AsyncClient


async def test__api__get_catalog__returns_hardware_annotated_models(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/catalog")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hardware"]["gpu_vendor"] == "nvidia"
    assert data["allow_custom"] is True  # settings.ollama.allow_custom_models default
    assert len(data["models"]) > 0
    names = [m["name"] for m in data["models"]]
    assert "qwen2.5:0.5b" in names
    # The generous 24GB-VRAM fake GPU should make every curated model runnable.
    assert all(m["runnable"] for m in data["models"])
    # Exactly one model is picked as the single best default for the hardware.
    assert sum(1 for m in data["models"] if m["recommended"]) == 1


async def test__api__get_catalog__each_model_has_expected_shape(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/catalog")

    assert resp.status_code == 200, resp.text
    [model] = [m for m in resp.json()["models"] if m["name"] == "qwen2.5:0.5b"]
    assert model["label"] == "Qwen2.5 0.5B"
    assert model["family"] == "Qwen2.5"
    assert model["params_b"] == 0.5
    assert isinstance(model["tasks"], list)
    assert isinstance(model["note"], str)
    assert model["note"]
