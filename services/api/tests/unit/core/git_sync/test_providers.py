from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.git_sync import providers as p

_CONTRACT = Path(__file__).resolve().parents[6] / "contracts" / "git-sync"
_CASES: dict[str, Any] = json.loads((_CONTRACT / "provider_cases.json").read_text(encoding="utf-8"))
_CATALOG_COPY = Path(p.__file__).with_name("providers.json")


def _link(link: p.ProviderLink | None) -> dict[str, Any] | None:
    return None if link is None else {"kind": link.kind.value, "url": link.url, "broad": link.broad}


def _case_id(case: dict[str, Any]) -> str:
    return str(case.get("name") or case.get("host") or case.get("provider") or case.get("text") or case)


def test__catalog_copy__equals_contract_file__byte_for_byte() -> None:
    assert _CATALOG_COPY.read_bytes() == (_CONTRACT / "providers.json").read_bytes()


def test__catalog__lists_every_provider_once_with_known_auth_variants() -> None:
    raw = json.loads(_CATALOG_COPY.read_text(encoding="utf-8"))
    ids = [spec.id.value for spec in p.catalog().providers]

    assert ids == [item["id"] for item in raw["providers"]]
    assert sorted(ids) == sorted(provider.value for provider in p.GitProvider)
    for spec in p.catalog().providers:
        assert set(spec.auth_variants) <= set(raw["auth_variants"])
        # Сервер Студии выдаёт токен только входом по коду устройства.
        assert ("device" if spec.id is p.GitProvider.hse_studio else "token") in spec.auth_variants


def test__catalog__hse_studio_is_detected_only_by_its_info_endpoint() -> None:
    spec = p.provider_spec("hse_studio")

    assert spec.host_rules == ()
    assert spec.api.detect == p.ApiDetect(
        path="/git/-/info", version_header=None, version_key="server", value="hse-doc-studio"
    )
    assert spec.auth_variants == ("device",)
    assert spec.token_primary is None


def test__catalog__github_limits_follow_the_documented_ones() -> None:
    spec = p.provider_spec("github")

    assert (spec.name_limit, spec.description_limit) == (40, 1024)


def test__catalog__token_links_never_ask_for_the_api_scope() -> None:
    for spec in p.catalog().providers:
        assert "api" not in spec.permissions.required
        for link in (spec.token_primary, spec.token_fallback):
            if link is not None:
                assert "api" not in [value for _, value in link.query]


@pytest.mark.parametrize("case", _CASES["host_cases"], ids=_case_id)
def test__detect_provider__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    overrides = {host: p.GitProvider(name) for host, name in case.get("overrides", {}).items()}
    api = case.get("api")

    info = p.detect_provider(
        case["host"],
        overrides=overrides or None,
        api=p.ApiDetection(p.GitProvider(api["provider"]), api["version"]) if api else None,
    )

    assert {"id": info.id.value, "detected_by": info.detected_by.value, "version": info.version} == case["expect"]


@pytest.mark.parametrize("case", _CASES["web_base_cases"], ids=_case_id)
def test__web_base__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    result = p.web_base(host=case["host"], port=case["port"], secure=case["secure"], subpath=case["subpath"])

    assert result == case["expect"]


@pytest.mark.parametrize("case", _CASES["api_base_cases"], ids=_case_id)
def test__api_base__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    assert p.api_base(case["provider"], host=case["host"], base=case["web_base"]) == case["expect"]


@pytest.mark.parametrize("case", _CASES["prefix_cases"], ids=_case_id)
def test__instance_prefix_candidates__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    assert p.instance_prefix_candidates(case["segments"]) == case["expect"]


@pytest.mark.parametrize("case", _CASES["text_cases"], ids=_case_id)
def test__text_helpers__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    kind = case["kind"]
    if kind == "token_name":
        assert p.default_token_name(case["project"]) == case["expect"]
    elif kind == "token_description":
        assert p.default_token_description(date.fromisoformat(case["date"]), case["lang"]) == case["expect"]
    elif kind == "clean_text":
        assert p.clean_text(case["text"], case["limit"]) == case["expect"]
    else:
        assert p.encode_component(case["text"]) == case["expect"]


@pytest.mark.parametrize("case", _CASES["token_link_cases"], ids=_case_id)
def test__token_links__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    links = p.token_links(
        case["provider"],
        web_base=case["web_base"],
        name=case["token_name"],
        description=case["description"],
        owner=case["owner"],
        repo=case["repo"],
        expires_in_days=case["expires_in_days"],
    )

    assert {"primary": _link(links.primary), "fallback": _link(links.fallback)} == case["expect"]


@pytest.mark.parametrize("case", _CASES["ssh_link_cases"], ids=_case_id)
def test__ssh_links__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    links = p.ssh_links(case["provider"], web_base=case["web_base"], owner=case["owner"], repo=case["repo"])

    assert {"user_keys": _link(links.user_keys), "deploy_key": _link(links.deploy_key)} == case["expect"]


@pytest.mark.parametrize("case", _CASES["scope_cases"], ids=lambda c: f"{c['provider']}-{c['scopes']}")
def test__assess_scopes__shared_vector__matches_expected(case: dict[str, Any]) -> None:
    result = p.assess_scopes(case["provider"], case["scopes"])

    assert {"sufficiency": result.sufficiency.value, "missing": list(result.missing)} == case["expect"]


def test__token_links__gitlab_primary__asks_exactly_the_git_scopes() -> None:
    links = p.token_links("gitlab", web_base="https://gitlab.com", name="n", description="d")

    assert links.primary is not None
    assert links.primary.url.endswith("&scopes=read_repository,write_repository")


def test__token_links__long_description__is_cut_to_the_github_limit_before_encoding() -> None:
    links = p.token_links("github", web_base="https://github.com", name="n", description="ab " * 600)

    assert links.primary is not None
    description = links.primary.url.split("description=")[1].split("&")[0]
    assert len(description.replace("%20", " ")) <= 1024


@pytest.mark.parametrize("base", ["gitlab.com", "ftp://gitlab.com", "https://gitlab.com/?x=1", "https://git lab.com"])
def test__token_links__invalid_web_base__raises(base: str) -> None:
    with pytest.raises(ValueError, match="web_base"):
        p.token_links("gitlab", web_base=base, name="n", description="d")


def test__provider_for_host__is_case_insensitive_and_none_safe() -> None:
    assert p.provider_for_host("GitLab.COM") is p.GitProvider.gitlab
    assert p.provider_for_host(None) is p.GitProvider.other
