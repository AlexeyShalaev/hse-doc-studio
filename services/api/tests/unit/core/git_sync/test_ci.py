from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.ci import CiProvider, CiPublish, CiTrigger, parse_ci_options
from hse_doc_studio.core.git_sync.error_classifier import GitOp, Transport, classify_git_stderr
from hse_doc_studio.core.git_sync.errors import GitErrorCode

_DEFAULT_IMAGE = "ghcr.io/alexeyshalaev/hse-doc-studio:0.2.0"
_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "git_stderr"


def _parse(**overrides: object):  # noqa: ANN202
    args: dict[str, object] = {
        "provider": "github",
        "docs": "all",
        "publish": "artifacts",
        "triggers": ["push"],
        "image": None,
        "default_image": _DEFAULT_IMAGE,
    }
    args.update(overrides)
    return parse_ci_options(**args)  # type: ignore[arg-type]


def test__parse_ci_options__minimal_request__uses_default_image_and_all_documents() -> None:
    options = _parse()

    assert options.provider is CiProvider.github
    assert options.publish is CiPublish.artifacts
    assert options.docs is None
    assert options.image == _DEFAULT_IMAGE
    assert options.path == ".github/workflows/hse-studio-build.yml"
    assert options.command == "hse-doc-studio build . --all --out build"


def test__parse_ci_options__gitlab__file_lies_in_the_project_root() -> None:
    assert _parse(provider="gitlab").path == ".gitlab-ci.yml"


def test__parse_ci_options__docs_list__keeps_order_and_drops_repeats() -> None:
    options = _parse(docs=["vkr--ivanov", "tz", "vkr--ivanov"])

    assert options.docs == ("vkr--ivanov", "tz")
    assert options.command == "hse-doc-studio build . --docs vkr--ivanov tz --out build"


def test__parse_ci_options__triggers__are_ordered_and_deduplicated() -> None:
    options = _parse(triggers=["manual", "tag", "push", "tag"])

    assert options.triggers == (CiTrigger.push, CiTrigger.tag, CiTrigger.manual)


def test__parse_ci_options__custom_image__replaces_the_default() -> None:
    assert _parse(image=" registry.example.org/team/studio:1.2 ").image == "registry.example.org/team/studio:1.2"


def test__parse_ci_options__blank_image__falls_back_to_default() -> None:
    assert _parse(image="  ").image == _DEFAULT_IMAGE


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "bitbucket"},
        {"publish": "pages"},
        {"triggers": []},
        {"triggers": ["schedule"]},
        {"docs": []},
        {"publish": "release", "triggers": ["push"]},
    ],
    ids=["provider", "publish", "no-triggers", "trigger", "no-docs", "release-without-tag"],
)
def test__parse_ci_options__invalid_request__raises_value_error(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — текст ошибки служебный
        _parse(**overrides)


@pytest.mark.parametrize(
    "doc_id",
    ["a; rm -rf /", "$(id)", "a b", "a\nb", "-x", "a'b", "a`b`", "", "../x", "а"],
)
def test__parse_ci_options__shell_unsafe_document_id__is_rejected(doc_id: str) -> None:
    with pytest.raises(ValueError, match="document id"):
        _parse(docs=[doc_id])


@pytest.mark.parametrize("image", ["x y", "img;rm", "img\nname", "-img", "img$(id)", "a" * 201])
def test__parse_ci_options__unsafe_image__is_rejected(image: str) -> None:
    with pytest.raises(ValueError, match="image"):
        _parse(image=image)


def test__classify_git_stderr__push_of_workflow_file_without_scope__is_workflow_scope_missing() -> None:
    text = (_FIXTURES / "workflow_scope_missing__push__https__pat_without_scope.txt").read_text(encoding="utf-8")

    result = classify_git_stderr(text, op=GitOp.push, transport=Transport.https)

    assert result.code is GitErrorCode.workflow_scope_missing
