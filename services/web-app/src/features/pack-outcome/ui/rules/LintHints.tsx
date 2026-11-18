import { CircleAlert, Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeElementRef } from "@entities/pack-studio";
import { touches } from "../../lib/lint";
import { useOutcomeModel } from "../../model";
import { useCachedLint } from "../useLintCounts";

const ICON = { error: CircleAlert, warning: TriangleAlert, info: Info };
/** Сколько находок показать кратко: остальные в режиме «Проверка». */
const SHOWN = 2;

type LintHintsProps = { element: OutcomeElementRef };

/**
 * Находки линтера по выбранному элементу, кратко и со ссылкой на режим «Проверка». Берутся из кэша:
 * режим «Проверка» считает, панель «Почему?» лишь показывает, что уже посчитано. Нет находок или
 * проверка ещё не запускалась: ничего не рисуется.
 */
export const LintHints = ({ element }: LintHintsProps) => {
  const { t } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const lint = useCachedLint();
  const found = (lint?.findings ?? []).filter((finding) =>
    touches(finding, element),
  );
  if (found.length === 0) return null;
  return (
    <section
      className="po-lint-hints"
      aria-label={t("lint.rules.title")}
      data-testid="outcome-rules-lint"
    >
      <h4 className="po-lint-hints-title">
        {t("lint.rules.count", { count: found.length })}
      </h4>
      <ul className="po-lint-hints-list">
        {found.slice(0, SHOWN).map((finding, index) => {
          const Icon = ICON[finding.severity];
          return (
            <li
              key={`${finding.rule_id}-${String(index)}`}
              data-severity={finding.severity}
            >
              <Icon size="0.8125rem" aria-hidden="true" />
              <span className="sr-only">
                {t(`lint.severity.${finding.severity}`)}:{" "}
              </span>
              <span>{finding.message}</span>
            </li>
          );
        })}
      </ul>
      {found.length > SHOWN && (
        <p className="po-note">
          {t("lint.rules.more", { count: found.length - SHOWN })}
        </p>
      )}
      <button
        type="button"
        className="btn sm"
        data-testid="outcome-rules-lint-open"
        onClick={() => {
          url.update({ view: "lint", tab: "result" }, true);
        }}
      >
        {t("lint.rules.open")}
      </button>
    </section>
  );
};
