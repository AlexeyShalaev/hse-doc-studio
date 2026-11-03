"""Словари писем: ru и en совпадают по ключам и подстановкам, нет лишних видов и длинных тире со стрелками."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from pathlib import Path

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.catalog import PLURAL_FORMS, catalog, placeholders
from hse_doc_studio.core.mail.samples import _SAMPLES

_LOCALES = Path(__file__).resolve().parents[4] / "hse_doc_studio" / "core" / "mail" / "locales"
_REQUIRED = ("subject", "preheader", "title", "lead")
_BANNED = ("—", "–", "→", "←", "⇒", "->", "<-", "=>")
# Формы множественного числа различаются по языкам, остальное зеркально.
_PER_LANGUAGE = ("layout.duration",)


def _walk(node: object, prefix: str = "") -> Iterator[tuple[str, object]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if path in _PER_LANGUAGE:
                yield path, None
            else:
                yield from _walk(value, path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{prefix}[{index}]")
    else:
        yield prefix, node


def _strings(lang: Lang) -> dict[str, str]:
    return {path: value for path, value in _walk(catalog(lang)) if isinstance(value, str)}


def test__locale_files__exist_for_every_language_and_parse() -> None:
    for lang in Lang:
        assert json.loads((_LOCALES / f"{lang.value}.json").read_text(encoding="utf-8"))


def test__ru_and_en__have_the_same_keys() -> None:
    ru, en = _strings(Lang.ru), _strings(Lang.en)

    assert sorted(set(ru) - set(en)) == []
    assert sorted(set(en) - set(ru)) == []


def test__ru_and_en__use_the_same_placeholders_in_every_string() -> None:
    ru, en = _strings(Lang.ru), _strings(Lang.en)

    differing = {path for path in ru if placeholders(ru[path]) != placeholders(en[path])}
    assert sorted(differing) == []


def test__ru_and_en__no_empty_strings_and_no_banned_characters() -> None:
    for lang in Lang:
        for path, text in _strings(lang).items():
            assert text.strip(), (lang, path)
            assert not any(mark in text for mark in _BANNED), (lang, path)
            assert "  " not in text, (lang, path)


def test__every_template_has_texts_in_both_languages_and_nothing_extra() -> None:
    for lang in Lang:
        mails = catalog(lang)["mails"]
        assert set(mails) == {t.value for t in MailTemplate}
        for name, texts in mails.items():
            for key in _REQUIRED:
                assert texts.get(key), (lang, name, key)
            for row in texts.get("details", []):
                assert len(row) == 2, (lang, name)


def test__every_template_has_a_sample() -> None:
    assert set(_SAMPLES) == set(MailTemplate)


def test__plural_forms__are_complete_for_each_language() -> None:
    for lang in Lang:
        for unit, forms in catalog(lang)["layout"]["duration"].items():
            assert set(forms) == set(PLURAL_FORMS[lang]), (lang, unit)
            assert all("{n}" in form for form in forms.values())


def test__roles__are_translated_in_both_languages() -> None:
    assert set(catalog(Lang.ru)["roles"]) == set(catalog(Lang.en)["roles"]) == {"reader", "reviewer", "editor", "owner"}


def test__texts__contain_no_markup_only_placeholders() -> None:
    markup = re.compile(r"<[a-zA-Z/]")
    for lang in Lang:
        for path, text in _strings(lang).items():
            assert not markup.search(text), (lang, path)
