from __future__ import annotations

import pytest
from hse_doc_studio.infra.ai.ollama.registry import OllamaRegistryClient, _parse_search_html

_FIXTURE = """
<ul role="list">
  <li x-test-model class="flex">
    <a href="/library/qwen3.5" class="group">
      <h2><span x-test-search-response-title>qwen3.5</span></h2>
      <p class="max-w-lg text-md">Qwen 3.5 is a family of open-source models with &amp; great utility.</p>
      <span x-test-capability class="x">vision</span>
      <span x-test-capability class="x">tools</span>
      <span x-test-size class="y">7b</span>
      <span x-test-pull-count>12.9M Pulls</span>
    </a>
  </li>
  <li x-test-model class="flex">
    <a href="/library/qwen2.5" class="group">
      <h2><span x-test-search-response-title>qwen2.5</span></h2>
      <p class="max-w-lg text-md">Qwen2.5 models pretrained on a large dataset.</p>
      <span x-test-pull-count>31.8M Pulls</span>
    </a>
  </li>
</ul>
"""


@pytest.mark.unit
def test__parse_search_html__extracts_models_via_test_hooks() -> None:
    models = _parse_search_html(_FIXTURE)

    assert [m.name for m in models] == ["qwen3.5", "qwen2.5"]
    first = models[0]
    assert "open-source" in first.description
    assert "&" in first.description  # HTML entity unescaped
    assert first.pulls == "12.9M Pulls"
    assert first.capabilities == ["vision", "tools"]
    assert models[1].capabilities == []


@pytest.mark.unit
def test__parse_search_html__no_models__returns_empty() -> None:
    assert _parse_search_html("<html><body>nothing here</body></html>") == []


@pytest.mark.unit
async def test__registry_search__blank_query__returns_empty_without_network() -> None:
    # Empty query must short-circuit (no HTTP) — verified by it not raising even
    # with an unreachable URL.
    client = OllamaRegistryClient(search_url="http://127.0.0.1:1/search", timeout_s=0.1)
    assert await client.search("   ") == []
