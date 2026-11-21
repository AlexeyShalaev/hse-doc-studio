import { Info, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSituationDelta } from "./useSituationDelta";

/**
 * Плашка «что изменилось» над результатом: после смены условия одной строкой, на сколько
 * изменился результат (числа даёт сравнение на сервере). «Показать только изменившееся»
 * включает фильтр центра, «Скрыть» убирает плашку и подсветку.
 */
export const DeltaStrip = () => {
  const { t } = useTranslation("packSpace");
  const delta = useSituationDelta();
  if (!delta.active) return null;
  const { summary } = delta;
  return (
    <div
      className="sp-delta"
      role="status"
      data-status={delta.status}
      data-testid="sp-delta"
    >
      <Info size="0.9375rem" aria-hidden="true" />
      <div className="sp-delta-text">
        {delta.status === "loading" ? (
          <span>{t("situation.delta.loading")}</span>
        ) : delta.status === "error" ? (
          <span>{t("situation.delta.failed")}</span>
        ) : summary?.identical ? (
          <span>{t("situation.delta.same", { label: delta.label })}</span>
        ) : (
          <span>
            {t("situation.delta.changed", { label: delta.label })}{" "}
            {summary?.parts.map((part) => (
              <span key={part.section} className="sp-delta-part">
                <b>{t(`situation.sections.${part.section}`)}</b>{" "}
                {[
                  part.added > 0
                    ? t("situation.delta.added", { count: part.added })
                    : "",
                  part.changed > 0
                    ? t("situation.delta.edited", { count: part.changed })
                    : "",
                  part.removed > 0
                    ? t("situation.delta.removed", { count: part.removed })
                    : "",
                ]
                  .filter((text) => text !== "")
                  .join(", ")}
                {". "}
              </span>
            ))}
          </span>
        )}
      </div>
      {delta.status === "error" ? (
        <button type="button" className="btn sm" onClick={delta.retry}>
          {t("situation.retry")}
        </button>
      ) : null}
      {delta.status === "ready" && !summary?.identical ? (
        <button
          type="button"
          className="btn sm"
          aria-pressed={delta.onlyChanged}
          data-testid="sp-delta-only"
          onClick={delta.toggleOnly}
        >
          {t(
            delta.onlyChanged
              ? "situation.delta.showAll"
              : "situation.delta.showOnly",
          )}
        </button>
      ) : null}
      <button
        type="button"
        className="icon-btn sm"
        aria-label={t("situation.delta.hide")}
        title={t("situation.delta.hide")}
        data-testid="sp-delta-hide"
        onClick={delta.dismiss}
      >
        <X size="0.9375rem" aria-hidden="true" />
      </button>
    </div>
  );
};
