import { CircleAlert, TriangleAlert, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { findingTarget, type LintFailure } from "@entities/pack-studio";

export type GateFindingsProps = {
  failure: LintFailure;
  onOpen: (path: string, line: number | null) => void;
  onDismiss: () => void;
};

/**
 * Находки проверки пака перед отправкой (lint_failed у «Предложить изменения»,
 * template-studio.md, 4.4): путь файла или каталога без строки. Клик ведёт в файл
 * (или манифест версии), строку и полный список даёт линтер версии ниже.
 */
export const GateFindings = ({
  failure,
  onOpen,
  onDismiss,
}: GateFindingsProps) => {
  const { t } = useTranslation("packStudio");
  return (
    <section className="ps-gate" data-testid="problems-gate">
      <div className="ps-problems-head">
        <h3 className="ps-problems-group">{t("problems.gate.title")}</h3>
        <button
          type="button"
          className="icon-btn"
          title={t("problems.gate.dismiss")}
          aria-label={t("problems.gate.dismiss")}
          onClick={onDismiss}
          data-testid="problems-gate-dismiss"
        >
          <X size="0.75rem" />
        </button>
      </div>
      <p className="ps-problems-scope">
        {t("problems.gate.lead", { count: failure.errors })}
      </p>
      <ul className="ps-problem-list">
        {failure.findings.map((finding, index) => {
          const target = findingTarget(finding.path, finding.message);
          const Icon =
            finding.severity === "error" ? CircleAlert : TriangleAlert;
          const body = (
            <>
              <Icon
                size="0.8125rem"
                aria-hidden="true"
                className={clsx(
                  "ps-problem-icon",
                  `ps-problem-${finding.severity}`,
                )}
              />
              <span className="ps-problem-text">
                <span className="ps-problem-message">{finding.message}</span>
                <span className="ps-problem-where">
                  {[
                    finding.check,
                    target?.path ?? finding.path,
                    target?.line
                      ? t("problems.line", { line: target.line })
                      : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
            </>
          );
          return (
            <li
              key={`${finding.path}:${String(index)}`}
              data-severity={finding.severity}
              data-testid="gate-item"
            >
              {target ? (
                <button
                  type="button"
                  className="ps-problem"
                  onClick={() => {
                    onOpen(target.path, target.line);
                  }}
                >
                  {body}
                </button>
              ) : (
                <div className="ps-problem">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
};
