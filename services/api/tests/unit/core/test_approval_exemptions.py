"""Исключения из одобрения: разбор строк и совпадение адреса с правилом."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.identity.approval_exemptions import (
    MAX_RULES,
    ExemptionIssue,
    ExemptionProblem,
    ExemptionRulesError,
    describe_problems,
    matching_rule,
    normalize_rules,
    parse_rule,
    parse_rules,
    rule_matches,
)

ISSUE = ExemptionIssue


@pytest.mark.parametrize(
    ("raw", "rule"),
    [
        ("hse.ru", "hse.ru"),
        ("  HSE.Ru ", "hse.ru"),
        ("@hse.ru", "hse.ru"),
        ("*.hse.ru", "*.hse.ru"),
        ("*.EDU.HSE.RU", "*.edu.hse.ru"),
        ("Name@Example.COM", "name@example.com"),
        ("first.last+tag@hse.ru", "first.last+tag@hse.ru"),
        ("ВШЭ.РФ", "вшэ.рф"),
        ("*.Пример.рф", "*.пример.рф"),
        ("xn--80aswg.xn--p1ai", "xn--80aswg.xn--p1ai"),
        ("my-uni.ac.uk", "my-uni.ac.uk"),
    ],
)
def test_parse_rule_normalizes(raw: str, rule: str) -> None:
    assert parse_rule(raw) == rule


@pytest.mark.parametrize(
    ("raw", "issue"),
    [
        ("hse", ISSUE.domain),
        ("hse..ru", ISSUE.domain),
        ("hse.ru.", ISSUE.domain),
        ("-hse.ru", ISSUE.domain),
        ("hse_x.ru", ISSUE.domain),
        ("hse ru", ISSUE.domain),
        (".hse.ru", ISSUE.domain),
        ("*.ru", ISSUE.domain),
        ("hse.ru$", ISSUE.domain),
        ("^.*@hse\\.ru$", ISSUE.wildcard),
        ("*hse.ru", ISSUE.wildcard),
        ("hse.*", ISSUE.wildcard),
        ("*.*.hse.ru", ISSUE.wildcard),
        ("*@hse.ru", ISSUE.wildcard),
        ("name@*.hse.ru", ISSUE.wildcard),
        ("a@b@hse.ru", ISSUE.address),
        ("name@hse", ISSUE.address),
        ("na me@hse.ru", ISSUE.address),
        ("a" * 260 + ".ru", ISSUE.too_long),
        ("a" * 64 + ".ru", ISSUE.domain),
    ],
)
def test_parse_rule_rejects(raw: str, issue: ExemptionIssue) -> None:
    with pytest.raises(ValueError, match=issue.value):
        parse_rule(raw)


def test_parse_rules_skips_blanks_dedupes_and_keeps_order() -> None:
    assert parse_rules(["*.hse.ru", "", "  ", "HSE.ru", "hse.ru", "a@b.org"]) == ("*.hse.ru", "hse.ru", "a@b.org")


def test_parse_rules_reports_every_bad_line_with_its_number() -> None:
    with pytest.raises(ExemptionRulesError) as exc:
        parse_rules(["hse.ru", "", "hse", "*hse.ru"])

    assert exc.value.problems == (
        ExemptionProblem(3, "hse", ISSUE.domain),
        ExemptionProblem(4, "*hse.ru", ISSUE.wildcard),
    )
    assert not exc.value.too_many


def test_parse_rules_limits_count() -> None:
    lines = [f"u{i}@hse.ru" for i in range(MAX_RULES)]
    assert len(parse_rules(lines)) == MAX_RULES
    with pytest.raises(ExemptionRulesError) as exc:
        parse_rules([*lines, "extra@hse.ru"])
    assert exc.value.too_many
    assert exc.value.problems == ()


def test_describe_problems_in_both_languages() -> None:
    problems = [ExemptionProblem(2, "hse", ISSUE.domain)]
    assert describe_problems(problems, too_many=False, lang="ru") == (
        "Строка 2 «hse»: это не домен, ожидается вид hse.ru"
    )
    assert describe_problems(problems, too_many=True, lang="en").startswith("Line 2 'hse': not a domain")
    assert "100" in describe_problems([], too_many=True, lang="en")


def test_normalize_rules_drops_garbage_from_storage() -> None:
    assert normalize_rules(["HSE.ru", "hse", "*.hse.ru", "hse.ru"]) == ("hse.ru", "*.hse.ru")


@pytest.mark.parametrize(
    ("rule", "email", "matches"),
    [
        ("hse.ru", "ann@hse.ru", True),
        ("hse.ru", "Ann@HSE.RU", True),
        ("hse.ru", " ann@hse.ru ", True),
        ("hse.ru", "ann@nothse.ru", False),
        ("hse.ru", "ann@hse.ru.evil.com", False),
        ("hse.ru", "ann@edu.hse.ru", False),
        ("hse.ru", "hse.ru@gmail.com", False),
        ("*.hse.ru", "ann@edu.hse.ru", True),
        ("*.hse.ru", "ann@a.b.hse.ru", True),
        ("*.hse.ru", "ann@hse.ru", False),
        ("*.hse.ru", "ann@nothse.ru", False),
        ("*.hse.ru", "ann@edu.hse.ru.evil.com", False),
        ("*.hse.ru", "ann@evil-hse.ru", False),
        ("name@example.com", "NAME@example.com", True),
        ("name@example.com", "other@example.com", False),
        ("name@example.com", "name@sub.example.com", False),
        ("вшэ.рф", "анна@ВШЭ.РФ", True),
        ("*.вшэ.рф", "анна@учёба.вшэ.рф", True),
    ],
)
def test_rule_matches(rule: str, email: str, matches: bool) -> None:
    assert rule_matches(rule, email) is matches


def test_matching_rule_returns_first_match() -> None:
    rules = ("rector@hse.ru", "hse.ru", "*.hse.ru")
    assert matching_rule("rector@hse.ru", rules) == "rector@hse.ru"
    assert matching_rule("ann@hse.ru", rules) == "hse.ru"
    assert matching_rule("ann@edu.hse.ru", rules) == "*.hse.ru"
    assert matching_rule("ann@gmail.com", rules) is None
    assert matching_rule("ann@hse.ru", ()) is None
