"""Поиск выделения из превью PDF в исходнике LaTeX: ручные случаи и случайные выделения из «отрисованной» главы."""

from __future__ import annotations

import random
import re

import pytest
from hse_doc_studio.core.review.pdf_match import fold_text, locate_in_source, project_source, visible_text

from tests.unit.core.review.pdf_corpus import CASES, SOURCE, Case, page_text, render


def _line_of(fragment: str) -> int:
    return SOURCE[: SOURCE.index(fragment)].count("\n") + 1 if fragment in SOURCE else 30


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test__locate_in_source__selection_from_pdf__finds_source_fragment(case: Case) -> None:
    found = locate_in_source(SOURCE, [_line_of(case.starts or "")], case.pdf)

    if case.starts is None:
        assert found is None
        return
    assert found is not None
    quote = SOURCE[found.start : found.end]
    assert quote.startswith(case.starts)
    assert case.ends is None or quote.endswith(case.ends)


def test__locate_in_source__same_phrase_twice__takes_the_one_near_synctex_line() -> None:
    source = "Первый абзац про метод.\n" + "Текст.\n" * 30 + "Второй абзац про метод.\n"
    near_second = source.count("\n")

    found = locate_in_source(source, [near_second], "про метод")

    assert found is not None
    assert found.start == source.rindex("про метод")


def test__locate_in_source__far_from_line_but_unique__is_found_in_whole_file() -> None:
    source = "Вступление.\n" * 200 + "Уникальная фраза для проверки поиска.\n"

    found = locate_in_source(source, [1], "Уникальная фраза для проверки поиска")

    assert found is not None
    assert source[found.start : found.end] == "Уникальная фраза для проверки поиска"


def test__project_source__drops_comments_commands_and_reference_keys() -> None:
    hay, offsets = project_source("Ссылка~\\cite[с.~5]{key} и \\textbf{жир}. % заметка\n")

    assert hay == "ссылкаижир"
    assert len(offsets) == len(hay)


def test__fold_text__ligatures_case_yo_and_punctuation() -> None:
    assert fold_text("Эффективный «ﬂow» — Ёлка, иссле-\nдование") == "эффективныиflowелкаисследование"


def test__visible_text__strips_markup_for_page_search() -> None:
    assert visible_text("по ГОСТ~7.32 и \\textbf{важно}~\\cite{k}.") == "по ГОСТ 7.32 и важно ."


def _random_selections(seed: int, count: int) -> tuple[int, int, int]:
    """(найдено верно, не найдено, найдено не там) на случайных выделениях из отрисованной главы."""
    rng = random.Random(seed)
    page = page_text(render(SOURCE), rng)
    words = [m.span() for m in re.finditer(r"\S+", page.text)]
    visible_all = set(project_source(SOURCE)[1])
    footnotes = visible_all - set(project_source(SOURCE, footnotes=False)[1])
    right = missed = wrong = 0
    while right + missed + wrong < count:
        first = rng.randrange(len(words))
        last = min(len(words) - 1, first + rng.randint(1, 30))
        lo, hi = words[first][0], words[last][1]
        selection = page.text[lo:hi]
        truth = {o for o in page.offsets[lo:hi] if o >= 0} & visible_all
        if len(fold_text(selection)) < 4 or not truth:
            continue
        line = SOURCE[: min(truth)].count("\n") + 1 + rng.randint(-3, 3)
        found = locate_in_source(SOURCE, [line], selection)
        if found is None:
            missed += 1
            continue
        got = (set(range(found.start, found.end)) & visible_all) - (footnotes - truth)
        overlap = len(truth & got) / len(truth | got)
        if overlap >= 0.8:
            right += 1
        else:
            wrong += 1
    return right, missed, wrong


@pytest.mark.parametrize("seed", [1, 2, 3])
def test__locate_in_source__random_selections__most_found_and_almost_none_misplaced(seed: int) -> None:
    right, missed, wrong = _random_selections(seed, 300)

    # Промахи это в основном выделения, захватившие текст сноски внизу страницы: такой тред уходит на PDF-якорь.
    assert right / 300 >= 0.9, (right, missed, wrong)
    assert wrong / 300 <= 0.02, (right, missed, wrong)
