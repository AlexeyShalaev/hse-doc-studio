"""Метрики журнала писем в /metrics (docs/design/mail-log.md, 8.2)."""

from __future__ import annotations

from hse_doc_studio.api.observability.mail_metrics import mail_collector
from hse_doc_studio.core.mail.journal import MailStatus
from hse_doc_studio.use_cases.mail.dispatch import MailCounters


def test__mail_collector__write_failures_are_always_exposed_even_at_zero() -> None:
    lines = list(mail_collector(MailCounters())())

    assert "hse_mail_log_write_failures_total 0" in lines
    assert not [line for line in lines if line.startswith("hse_mail_sent_total{")]


def test__mail_collector__attempts_by_kind_and_status() -> None:
    counters = MailCounters()
    counters.count("reset_password", MailStatus.sent)
    counters.count("reset_password", MailStatus.sent)
    counters.count("signing_reminder", MailStatus.failed)
    counters.count_write_failure()

    lines = list(mail_collector(counters)())

    assert "# TYPE hse_mail_sent_total counter" in lines
    assert 'hse_mail_sent_total{kind="reset_password",status="sent"} 2' in lines
    assert 'hse_mail_sent_total{kind="signing_reminder",status="failed"} 1' in lines
    assert "# TYPE hse_mail_log_write_failures_total counter" in lines
    assert "hse_mail_log_write_failures_total 1" in lines
