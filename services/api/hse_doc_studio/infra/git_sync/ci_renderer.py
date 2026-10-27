"""Рендер файлов CI из шаблонов в `ci_templates/` (GitHub Actions и GitLab CI)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from hse_doc_studio.core.git_sync.ci import (
    BUILD_OUT_DIR,
    RELEASE_TAG_GLOB,
    CiOptions,
    CiProvider,
    CiPublish,
    CiTrigger,
    RenderedCiFile,
)

_TEMPLATES = Path(__file__).resolve().parent / "ci_templates"

# YAML и shell полны `{{ }}`, `{% %}` и `${...}`, поэтому разметка шаблона пишется как `[[ ]]` и `[% %]`.
_ENV = Environment(  # noqa: S701 — вывод это YAML, не HTML; значения проверены в parse_ci_options
    loader=FileSystemLoader(_TEMPLATES),
    block_start_string="[%",
    block_end_string="%]",
    variable_start_string="[[",
    variable_end_string="]]",
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)

_TEMPLATE_NAMES = {CiProvider.github: "github.yml.j2", CiProvider.gitlab: "gitlab.yml.j2"}

_GITHUB_CONDITIONS = {
    CiTrigger.push: (
        "github.event_name == 'push' && github.ref_type == 'branch' "
        "&& github.ref_name == github.event.repository.default_branch"
    ),
    CiTrigger.tag: "github.event_name == 'push' && github.ref_type == 'tag'",
    CiTrigger.manual: "github.event_name == 'workflow_dispatch'",
}

_GITLAB_RULES = {
    CiTrigger.push: '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH',
    CiTrigger.tag: "$CI_COMMIT_TAG =~ /^v.+/",
    CiTrigger.manual: '$CI_PIPELINE_SOURCE == "web"',
}


class JinjaCiRenderer:
    def render(self, options: CiOptions) -> RenderedCiFile:
        triggers = set(options.triggers)
        context: dict[str, object] = {
            "image": options.image,
            "docs_args": options.docs_args,
            "out_dir": BUILD_OUT_DIR,
            "release": options.publish is CiPublish.release,
            "push": CiTrigger.push in triggers,
            "tag": CiTrigger.tag in triggers,
            "manual": CiTrigger.manual in triggers,
            "tag_glob": RELEASE_TAG_GLOB,
            "condition": " || ".join(_GITHUB_CONDITIONS[t] for t in options.triggers),
            "rules": [_GITLAB_RULES[t] for t in options.triggers],
        }
        content = _ENV.get_template(_TEMPLATE_NAMES[options.provider]).render(context)
        return RenderedCiFile(path=options.path, content=content)
