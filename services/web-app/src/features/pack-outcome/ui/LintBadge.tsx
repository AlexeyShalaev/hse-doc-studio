import { CircleAlert, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { type LintCounts } from "../lib/lint";
import { useOutcomeModel } from "../model";
import { useLintCounts } from "./useLintCounts";

type LintBadgeProps = {
  counts: LintCounts;
  /** Рядом с подписью вкладки: короче, без рамки. */
  inline?: boolean;
  testId?: string;
};

/**
 * Значок с числом ошибок и предупреждений. Уровень передаётся значком и словом, цвет не единственный
 * носитель смысла; программам экрана читается целая фраза.
 */
export const LintBadge = ({
  counts,
  inline = false,
  testId = "outcome-lint-badge",
}: LintBadgeProps) => {
  const { t } = useTranslation("packOutcome");
  const spoken =
    counts.errors + counts.warnings === 0
      ? t("lint.badge.clean")
      : t("lint.badge.spoken", {
          errors: t("lint.counts.errors", { count: counts.errors }),
          warnings: t("lint.counts.warnings", { count: counts.warnings }),
        });
  return (
    <span
      className="ln-badge"
      data-inline={inline ? "true" : undefined}
      data-clean={counts.errors + counts.warnings === 0 ? "true" : undefined}
      data-testid={testId}
      title={spoken}
    >
      <span className="sr-only">{spoken}</span>
      <span
        aria-hidden="true"
        className="ln-badge-part"
        data-severity="error"
        data-zero={counts.errors === 0 ? "true" : undefined}
      >
        <CircleAlert size="0.75rem" />
        {counts.errors}
      </span>
      <span
        aria-hidden="true"
        className="ln-badge-part"
        data-severity="warning"
        data-zero={counts.warnings === 0 ? "true" : undefined}
      >
        <TriangleAlert size="0.75rem" />
        {counts.warnings}
      </span>
    </span>
  );
};

/** Значок в верхней панели: клик открывает режим «Проверка». В режиме «Как студент» панели нет. */
export const LintBadgeButton = () => {
  const { t } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const counts = useLintCounts();
  if (!counts || url.state.mode === "student") return null;
  return (
    <button
      type="button"
      className="ln-badge-btn"
      title={t("lint.badge.open")}
      aria-label={t("lint.badge.open")}
      data-testid="outcome-lint-open"
      onClick={() => {
        url.update({ view: "lint" }, true);
      }}
    >
      <LintBadge counts={counts} testId="outcome-lint-bar-badge" />
    </button>
  );
};
