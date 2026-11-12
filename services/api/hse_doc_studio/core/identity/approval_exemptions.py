"""Исключения из одобрения администратором: адреса, которым после подтверждения почты одобрение не нужно.

Правило одной строкой:

- `hse.ru`: ровно этот домен;
- `*.hse.ru`: любой поддомен hse.ru, без самого hse.ru;
- `name@example.com`: один адрес.

Регулярных выражений нет намеренно: `hse.ru` как выражение пропустило бы `hseXru`, забытый `$` пропустил бы
`hse.ru.evil.com`, а неудачное выражение можно заставить считать очень долго (ReDoS). Три формы выше покрывают
настоящие случаи. Регистр и Unicode приводятся той же нормализацией, что разрешённые домены регистрации.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.identity.normalize import email_domain, normalize_domain, normalize_email

MAX_RULES = 100
MAX_RULE_LENGTH = 254
WILDCARD = "*."

# Метка домена: буквы (в том числе не латинские) и цифры, дефис внутри; до 63 символов.
_LABEL = re.compile(r"^(?!-)(?:[^\W_]|-){1,63}(?<!-)$")
# Локальная часть адреса: без пробелов, `@` и `*` (маски в адресе не поддерживаются).
_LOCAL = re.compile(r"^[^\s@*]{1,64}$")


class ExemptionIssue(StrEnum):
    """Почему строка не стала правилом; тексты на клиенте лежат по этим же ключам."""

    too_long = "too_long"
    wildcard = "wildcard"
    domain = "domain"
    address = "address"


@dataclass(frozen=True)
class ExemptionProblem:
    """Плохая строка списка: номер строки с единицы (пустые строки тоже считаются), текст и причина."""

    line: int
    value: str
    issue: ExemptionIssue


class ExemptionRulesError(ValueError):
    def __init__(self, problems: Sequence[ExemptionProblem], *, too_many: bool = False) -> None:
        self.problems = tuple(problems)
        self.too_many = too_many
        super().__init__(describe_problems(self.problems, too_many=too_many, lang="en"))


def _valid_domain(domain: str) -> bool:
    labels = domain.split(".")
    return len(domain) <= MAX_RULE_LENGTH and len(labels) >= 2 and all(_LABEL.match(label) for label in labels)


def _domain_rule(value: str) -> str:
    domain = normalize_domain(value)
    if "*" in domain:
        raise ValueError(ExemptionIssue.wildcard)
    if not _valid_domain(domain):
        raise ValueError(ExemptionIssue.domain)
    return domain


def _address_rule(value: str) -> str:
    address = normalize_email(value)
    if "*" in address:
        raise ValueError(ExemptionIssue.wildcard)
    local, _, domain = address.rpartition("@")
    if not _LOCAL.match(local) or not _valid_domain(domain):
        raise ValueError(ExemptionIssue.address)
    return address


def parse_rule(raw: str) -> str:
    """Нормализованное правило или `ValueError` с `ExemptionIssue` в `args[0]`."""
    value = raw.strip()
    if len(value) > MAX_RULE_LENGTH:
        raise ValueError(ExemptionIssue.too_long)
    # `@hse.ru` читается как домен, как и в списке разрешённых доменов.
    if "@" in value.lstrip("@"):
        return _address_rule(value)
    if value.startswith(WILDCARD):
        return WILDCARD + _domain_rule(value[len(WILDCARD) :])
    return _domain_rule(value)


def parse_rules(lines: Iterable[str]) -> tuple[str, ...]:
    """Строгий разбор для правки админом: пустые строки пропускаются, повторы схлопываются, порядок сохраняется.

    Любая плохая строка или больше `MAX_RULES` правил дают `ExemptionRulesError` со всеми найденными проблемами.
    """
    seen: dict[str, None] = {}
    problems: list[ExemptionProblem] = []
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            seen.setdefault(parse_rule(raw))
        except ValueError as error:
            problems.append(ExemptionProblem(number, raw.strip(), ExemptionIssue(error.args[0])))
    too_many = len(seen) > MAX_RULES
    if problems or too_many:
        raise ExemptionRulesError(problems, too_many=too_many)
    return tuple(seen)


def normalize_rules(lines: Iterable[str]) -> tuple[str, ...]:
    """Мягкий разбор сохранённого значения: негодные строки отбрасываются, лишние сверх предела тоже.

    Строгую проверку значение уже прошло при записи; здесь защита от ручной правки базы.
    """
    seen: dict[str, None] = {}
    for raw in lines:
        try:
            seen.setdefault(parse_rule(raw))
        except ValueError:
            continue
    return tuple(seen)[:MAX_RULES]


def rule_matches(rule: str, email: str) -> bool:
    if "@" in rule:
        return normalize_email(email) == rule
    domain = email_domain(email)
    if rule.startswith(WILDCARD):
        # Хвост с точкой: `*.hse.ru` не совпадает ни с `hse.ru`, ни с `nothse.ru`.
        return domain.endswith(rule[1:])
    return domain == rule


def matching_rule(email: str, rules: Iterable[str]) -> str | None:
    """Первое правило списка, под которое подходит адрес."""
    return next((rule for rule in rules if rule_matches(rule, email)), None)


_ISSUE_TEXT: dict[ExemptionIssue, tuple[str, str]] = {
    ExemptionIssue.too_long: ("слишком длинная строка", "the line is too long"),
    ExemptionIssue.wildcard: (
        "звёздочка допустима только в начале, как *.hse.ru",
        "an asterisk is allowed only at the start, as in *.hse.ru",
    ),
    ExemptionIssue.domain: ("это не домен, ожидается вид hse.ru", "not a domain, expected something like hse.ru"),
    ExemptionIssue.address: (
        "это не адрес, ожидается вид name@example.com",
        "not an address, expected something like name@example.com",
    ),
}


def describe_problems(problems: Sequence[ExemptionProblem], *, too_many: bool, lang: str) -> str:
    """Одна строка на каждую проблему, чтобы админ видел все сразу."""
    ru = lang != "en"
    parts = [
        (f"Строка {p.line} «{p.value}»: " if ru else f"Line {p.line} '{p.value}': ")
        + _ISSUE_TEXT[p.issue][0 if ru else 1]
        for p in problems
    ]
    if too_many:
        parts.append(
            f"Правил больше {MAX_RULES}: объедините адреса доменом."
            if ru
            else f"More than {MAX_RULES} rules: group addresses by domain."
        )
    return "; ".join(parts)
