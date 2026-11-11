"""Храповик журнала писем (docs/design/mail-log.md, L1): письмо уходит только через `MailDispatcher`.

`IMailSender.send` вызывает `use_cases/mail/dispatch.py`; он пишет строку журнала и метрику на каждую попытку.
Новый путь отправки мимо него не пройдёт CI, и журнал останется полным (цель 4).

Обход AST: вызовом почты считается `<что-то>.send(...)` в файле, который упоминает тип отправителя
(`IMailSender` или его реализации), и любой `.send(..., html=...)` с подписью письма где угодно в пакете.
"""

from __future__ import annotations

import ast
from pathlib import Path

import hse_doc_studio

_ROOT = Path(hse_doc_studio.__file__).resolve().parent
_SENDER_TYPES = frozenset({"IMailSender", "SmtpMailSender", "ConfiguredMailSender", "LinkOnlyMailSender"})
_DISPATCHER = "use_cases/mail/dispatch.py"
# Сам транспорт: реализации `IMailSender`, которые зовут вложенного отправителя или `aiosmtplib.send`.
_TRANSPORT = frozenset(
    {"infra/identity/smtp_mailer.py", "infra/identity/configured_mailer.py", "infra/identity/mail.py"}
)
# Временно, до перевода путей на диспетчер (раздел 12). Срез, который переводит путь, удаляет свою строку:
# тест ниже падает, если в файле из списка вызова уже нет.
_PENDING = {
    "infra/notifications/mailer.py": "B5: SmtpNotificationMailer, P8..P14",
}


def _identifiers(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add((node.asname or node.name).rpartition(".")[2])
    return found


def _send_calls(path: Path) -> list[int]:
    """Строки вызовов почты в файле."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    knows_sender = bool(_identifiers(tree) & _SENDER_TYPES)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "send"):
            continue
        mail_shaped = any(keyword.arg == "html" for keyword in node.keywords)
        if knows_sender or mail_shaped:
            lines.append(node.lineno)
    return sorted(lines)


def _all_calls() -> dict[str, list[int]]:
    calls: dict[str, list[int]] = {}
    for path in sorted(_ROOT.rglob("*.py")):
        lines = _send_calls(path)
        if lines:
            calls[path.relative_to(_ROOT).as_posix()] = lines
    return calls


def test__mail_is_sent_only_by_the_dispatcher() -> None:
    allowed = {_DISPATCHER} | _TRANSPORT | set(_PENDING)

    offenders = {path: lines for path, lines in _all_calls().items() if path not in allowed}

    assert offenders == {}, (
        "IMailSender.send вызывается мимо MailDispatcher (docs/design/mail-log.md, L1): "
        "отдайте письмо диспетчеру как MailRequest"
    )


def test__pending_exceptions_are_not_stale() -> None:
    calls = _all_calls()

    stale = {path: owner for path, owner in _PENDING.items() if path not in calls}

    assert stale == {}, "путь уже переведён на диспетчер: удалите его строку из _PENDING"


def test__the_detector_sees_the_dispatcher_call() -> None:
    assert _all_calls().get(_DISPATCHER), "детектор не нашёл вызов в самом диспетчере"
