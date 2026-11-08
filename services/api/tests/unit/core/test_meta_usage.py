"""Разбор динамических инклудов: какие макросы печатают поле проекта и какие документы его подключают."""

from __future__ import annotations

from hse_doc_studio.core.meta_usage import (
    input_targets,
    parse_include,
    printed_keys,
    referenced_keys,
    used_macros,
)

_META = r"""
% ((# АВТОГЕНЕРИРУЕМЫЙ ФАЙЛ: project.meta.ignored в комментарии не считается #))
\newcommand{\hseTitleEn}{%
((* if project.meta.name_en *)){{ project.meta.name_en | texesc }}((* else *))\hseFill{укажите}((* endif *))}
\newcommand{\hseProjectNameEn}{\hseTitleEn}
\newcommand{\hseYear}{%
{{ project.meta['year'] | default('') }}}
\newcommand{\hseSupervisorName}{%
{{ project.supervisor.name | default('') }}}
\newcommand{\signdateblank}{«\rule{0.8cm}{0.4pt}» \the\year~г.}
\newif\ifhseExtendedProposal
((* if project.meta.get('proposal_stage') *))\hseExtendedProposaltrue((* else *))\hseExtendedProposalfalse((* endif *))
\setmainfont{{ '{' }}{{ project.meta.font_main }}{{ '}' }}
"""


def test__parse_include__macro_bodies_aliases_flags_and_whole_lines() -> None:
    parsed = parse_include(_META)

    assert parsed.macros == {
        "name_en": {"hseTitleEn", "hseProjectNameEn"},
        "year": {"hseYear"},
        "supervisor": {"hseSupervisorName"},
        "proposal_stage": {"ifhseExtendedProposal"},
    }
    assert parsed.whole == {"font_main"}


def test__referenced_keys__meta_forms_and_people() -> None:
    text = "{{ project.meta.udc }} {{ project.meta['city'] }} {{ project.meta.get(\"faculty\") }} project.co_supervisor"

    assert referenced_keys(text) == {"udc", "city", "faculty", "co_supervisor"}


def test__used_macros_and_inputs__ignore_comments() -> None:
    text = "\\input{../common/meta}\n\\hseYear % \\hseCity\n% \\input{../common/fonts}\n\\ifhseExtendedProposal x\\fi"

    assert {"hseYear", "ifhseExtendedProposal"} <= used_macros(text)
    assert "hseCity" not in used_macros(text)
    assert input_targets(text) == ["../common/meta"]


def test__printed_keys__only_through_an_included_file() -> None:
    includes = {"common/meta": parse_include(_META)}

    with_meta = printed_keys(includes, {"hseProjectNameEn", "ifhseExtendedProposal"}, {"common/meta"}, {"udc"})
    without_meta = printed_keys(includes, {"hseProjectNameEn"}, set(), set())

    assert with_meta == {"name_en", "proposal_stage", "font_main", "udc"}
    assert without_meta == set()
