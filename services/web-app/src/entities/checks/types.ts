// "ok" is a check-result status (rule passed), not a severity level a user can
// set. It's grouped here because the SeverityMenu chip displays whatever
// severity comes through, including "ok" for results that passed.
// "skipped" is a check-result status too — the rule was auto-suppressed
// because the document is a custom upload (no readable .tex/log for that
// engine), a neutral state distinct from ok/warn/err.
export type Severity = "ok" | "warn" | "err" | "info" | "skipped";
