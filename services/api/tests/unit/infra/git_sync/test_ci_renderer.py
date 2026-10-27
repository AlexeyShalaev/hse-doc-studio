from __future__ import annotations

import itertools
from typing import Any

import pytest
import yaml
from hse_doc_studio.core.git_sync.ci import CiOptions, CiProvider, CiPublish, CiTrigger, parse_ci_options
from hse_doc_studio.infra.git_sync.ci_renderer import JinjaCiRenderer

_IMAGE = "ghcr.io/alexeyshalaev/hse-doc-studio:0.2.0"
_TRIGGER_SETS = [
    list(combo) for size in (1, 2, 3) for combo in itertools.combinations([t.value for t in CiTrigger], size)
]


def _options(
    provider: str, publish: str, triggers: list[str], docs: str | list[str] = "all", image: str | None = None
) -> CiOptions:
    return parse_ci_options(
        provider=provider, docs=docs, publish=publish, triggers=triggers, image=image, default_image=_IMAGE
    )


def _combinations(provider: CiProvider | None = None) -> list[tuple[str, str, list[str]]]:
    """Все допустимые сочетания; у релиза обязателен триггер tag."""
    return [
        (item.value, publish.value, triggers)
        for item in CiProvider
        if provider is None or item is provider
        for publish in CiPublish
        for triggers in _TRIGGER_SETS
        if publish is CiPublish.artifacts or CiTrigger.tag.value in triggers
    ]


def _render(options: CiOptions) -> tuple[str, dict[str, Any]]:
    text = JinjaCiRenderer().render(options).content
    return text, yaml.safe_load(text)


@pytest.mark.parametrize(("provider", "publish", "triggers"), _combinations())
def test__render__every_option_combination__is_valid_yaml_without_template_leftovers(
    provider: str, publish: str, triggers: list[str]
) -> None:
    text, data = _render(_options(provider, publish, triggers))

    assert isinstance(data, dict)
    assert "[[" not in text
    assert "[%" not in text
    assert text.endswith("\n")
    assert _IMAGE in text


@pytest.mark.parametrize(("_provider", "publish", "triggers"), _combinations(CiProvider.github))
def test__render__github__triggers_match_the_request(_provider: str, publish: str, triggers: list[str]) -> None:
    _, data = _render(_options("github", publish, triggers))

    on = data[True]  # YAML 1.1 читает ключ `on` как булево
    assert ("workflow_dispatch" in on) is ("manual" in triggers)
    assert ("push" in on) is bool({"push", "tag"} & set(triggers))
    assert ("branches" in on.get("push", {})) is ("push" in triggers)
    assert ("tags" in on.get("push", {})) is ("tag" in triggers)
    assert data["permissions"] == {"contents": "write" if publish == "release" else "read"}


def test__render__github_release__publishes_only_on_tags() -> None:
    _, data = _render(_options("github", "release", ["tag"]))

    steps = data["jobs"]["build"]["steps"]
    release = next(step for step in steps if step.get("name") == "Publish release")
    assert release["if"] == "github.ref_type == 'tag'"
    assert release["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "gh release create" in release["run"]


def test__render__github_artifacts__has_no_release_step() -> None:
    _, data = _render(_options("github", "artifacts", ["push"]))

    names = [step.get("name") for step in data["jobs"]["build"]["steps"]]
    assert names == [None, "Build documents", "Upload documents"]


def test__render__github__build_runs_pinned_image_with_listed_documents() -> None:
    text, data = _render(_options("github", "artifacts", ["manual"], docs=["tz", "vkr--ivanov"]))

    build = next(step for step in data["jobs"]["build"]["steps"] if step.get("name") == "Build documents")
    assert _IMAGE in build["run"]
    assert "hse-doc-studio build . --docs tz vkr--ivanov --out build" in build["run"]
    assert "/var/run/docker.sock" in text


def test__render__github__default_branch_gate_is_present_for_push() -> None:
    _, data = _render(_options("github", "artifacts", ["push"]))

    assert "github.event.repository.default_branch" in data["jobs"]["build"]["if"]


@pytest.mark.parametrize(("_provider", "publish", "triggers"), _combinations(CiProvider.gitlab))
def test__render__gitlab__rules_match_the_request(_provider: str, publish: str, triggers: list[str]) -> None:
    _, data = _render(_options("gitlab", publish, triggers))

    rules = [rule["if"] for rule in data["build-documents"]["rules"]]
    assert len(rules) == len(triggers)
    assert any("CI_DEFAULT_BRANCH" in rule for rule in rules) is ("push" in triggers)
    assert any("CI_COMMIT_TAG" in rule for rule in rules) is ("tag" in triggers)
    assert any('"web"' in rule for rule in rules) is ("manual" in triggers)
    assert ("release-documents" in data) is (publish == "release")
    assert data["stages"] == (["build", "release"] if publish == "release" else ["build"])


def test__render__gitlab__job_uses_pinned_image_and_docker_service() -> None:
    _, data = _render(_options("gitlab", "artifacts", ["push"], docs=["tz"]))

    job = data["build-documents"]
    assert job["image"]["name"] == _IMAGE
    assert job["script"] == ["hse-doc-studio build . --docs tz --out build"]
    assert job["services"][0]["alias"] == "docker"
    assert job["artifacts"]["paths"] == ["build/"]


def test__render__gitlab_release__links_to_the_build_artifacts() -> None:
    _, data = _render(_options("gitlab", "release", ["tag"]))

    release = data["release-documents"]
    assert release["needs"] == ["build-documents"]
    assert release["rules"] == [{"if": "$CI_COMMIT_TAG =~ /^v.+/"}]
    assert release["release"]["tag_name"] == "$CI_COMMIT_TAG"


def test__render__same_options__give_the_same_text() -> None:
    first, _ = _render(_options("github", "release", ["tag", "push"]))
    second, _ = _render(_options("github", "release", ["push", "tag"]))

    assert first == second


def test__render__custom_image__is_pinned_instead_of_default() -> None:
    text, _ = _render(_options("gitlab", "artifacts", ["manual"], image="registry.example.org/studio:1.0"))

    assert "registry.example.org/studio:1.0" in text
    assert _IMAGE not in text
