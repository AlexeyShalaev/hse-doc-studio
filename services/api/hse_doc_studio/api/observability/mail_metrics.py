"""Метрики журнала писем для /metrics (docs/design/mail-log.md, 8.2 и V16): попытки по виду и итогу, сбои записи
журнала, прекращённые автоповторы."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from hse_doc_studio.use_cases.mail.dispatch import MailCounters


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def mail_collector(counters: MailCounters) -> Callable[[], Iterable[str]]:
    """`hse_mail_sent_total{kind,status}` со строкой на каждую встреченную пару и `hse_mail_log_write_failures_total`
    всегда, даже с нулём: по нему ставят оповещение."""

    def collect() -> Iterable[str]:
        lines = [
            "# HELP hse_mail_sent_total Попытки отправить письмо по виду и итогу.",
            "# TYPE hse_mail_sent_total counter",
        ]
        for (kind, status), value in sorted(counters.attempts().items()):
            lines.append(f'hse_mail_sent_total{{kind="{_label(kind)}",status="{_label(status)}"}} {value}')
        lines += [
            "# HELP hse_mail_log_write_failures_total Строки журнала писем, которые не удалось записать.",
            "# TYPE hse_mail_log_write_failures_total counter",
            f"hse_mail_log_write_failures_total {counters.write_failures}",
            "# HELP hse_mail_retry_dropped_total Прекращённые автоповторы писем по причине.",
            "# TYPE hse_mail_retry_dropped_total counter",
        ]
        for reason, value in sorted(counters.dropped().items()):
            lines.append(f'hse_mail_retry_dropped_total{{reason="{_label(reason)}"}} {value}')
        return lines

    return collect
