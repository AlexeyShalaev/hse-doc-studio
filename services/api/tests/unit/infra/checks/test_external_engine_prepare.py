from __future__ import annotations

import pytest
from hse_doc_studio.infra.checks.external_engine import (
    _ignored,
    _prepare_text_for_lt,
)


@pytest.mark.unit
def test__prepare__preserves_line_count() -> None:
    src = (
        "% !TeX program = xelatex\n"
        "\\documentclass[12pt,a4paper]{extarticle}\n"
        "\\section{ВВЕДЕНИЕ}\n"
        "Текст со ссылкой~\\cite{gost19201} и \\verb|\\req{ТЗ-Ф-01}{...}|.\n"
        "\\begin{lstlisting}[language=Python]\n"
        'print("x")\n'
        "\\end{lstlisting}\n"
        "Конец.\n"
    )
    prepared = _prepare_text_for_lt(src)
    assert prepared.count("\n") == src.count("\n")


@pytest.mark.unit
def test__prepare__heading_becomes_sentence() -> None:
    prepared = _prepare_text_for_lt("\\section{Выбор стека}\nОпишите выбор.\n")
    assert "Выбор стека." in prepared
    assert "\\section" not in prepared


@pytest.mark.unit
def test__prepare__glued_cite_does_not_fuse_token() -> None:
    prepared = _prepare_text_for_lt("программных документов\\cite{gost}.\n")
    assert "документовN" not in prepared
    assert "документов." in prepared


@pytest.mark.unit
def test__prepare__spaced_ref_becomes_token() -> None:
    prepared = _prepare_text_for_lt("см. раздел~\\ref{sec:limits}).\n")
    assert "раздел N)." in prepared


@pytest.mark.unit
def test__prepare__hse_optional_keeps_prose() -> None:
    prepared = _prepare_text_for_lt("до этого. \\hseOptional{Репозиторий является закрытым.}\n")
    assert "Репозиторий является закрытым." in prepared
    assert "NРепозиторий" not in prepared


@pytest.mark.unit
def test__prepare__hse_fill_becomes_token() -> None:
    prepared = _prepare_text_for_lt("не~менее \\hseFill{укажите RPS} запросов\n")
    assert "не менее N запросов" in prepared


@pytest.mark.unit
def test__prepare__table_cells_become_sentences_without_double_dots() -> None:
    prepared = _prepare_text_for_lt("Задача решена. \\\\\nячейка один & Ячейка два \\\\\n")
    assert ".." not in prepared
    assert "ячейка один. Ячейка два" in prepared


@pytest.mark.unit
def test__prepare__comments_and_bibliography_removed() -> None:
    src = (
        "текст % TODO черновик - убрать\n"
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{gost} ГОСТ — Москва : Стандартинформ.\n"
        "\\end{thebibliography}\n"
    )
    prepared = _prepare_text_for_lt(src)
    assert "черновик" not in prepared
    assert "Стандартинформ" not in prepared
    assert prepared.count("\n") == src.count("\n")


@pytest.mark.unit
def test__prepare__language_switch_argument_is_not_prose() -> None:
    # \begin{otherlanguage}{russian} — переключатель babel: без снятия
    # аргумента «russian» уходил в LanguageTool отдельным словом и стабильно
    # возвращался как опечатка в англоязычном документе.
    src = "\\begin{otherlanguage}{russian}\nТекст реферата.\n\\end{otherlanguage}\n"
    prepared = _prepare_text_for_lt(src)
    assert "russian" not in prepared
    assert "Текст реферата." in prepared
    assert prepared.count("\n") == src.count("\n")


@pytest.mark.unit
def test__markup_artifact__placeholder_runs_and_punctuation() -> None:
    from hse_doc_studio.infra.checks.external_engine import _is_markup_artifact

    assert _is_markup_artifact("N N")
    assert _is_markup_artifact("N. N")
    assert _is_markup_artifact("+ . -")
    assert _is_markup_artifact(" :")
    assert not _is_markup_artifact("mention .")
    assert not _is_markup_artifact("the the")


@pytest.mark.unit
def test__ignored__exact_and_prefix() -> None:
    words = ["версионирован*", "-ы", "ГОСТов"]
    assert _ignored("Версионирование", words)
    assert _ignored("версионированию", words)
    assert _ignored("-ы", words)
    assert _ignored("гостов", words)
    assert not _ignored("версия", words)
    assert not _ignored("гостиница", words)


@pytest.mark.unit
def test__prepare__titleformat_with_mixed_argument_order__drops_the_whole_command() -> None:
    r"""Аргументы \titleformat идут как `{арг}[опция]{арг}…` — и все они разметка.

    Прежняя регулярка допускала только `[опция]?{арг}*[опция]?` и обрывалась на
    `[hang]`, из-за чего хвост `{1ex}{}` доезжал до LanguageTool прозой: `1ex`
    приходил опечаткой в каждом документе с приложениями.
    """
    src = (
        "\\titleformat{\\chapter}[hang]\n"
        "  {\\normalfont\\large\\bfseries\\centering}{Appendix~\\thechapter}{1ex}{}\n"
        "Real prose follows here.\n"
    )

    prepared = _prepare_text_for_lt(src)

    assert "1ex" not in prepared
    assert "hang" not in prepared
    assert "Real prose follows here." in prepared
