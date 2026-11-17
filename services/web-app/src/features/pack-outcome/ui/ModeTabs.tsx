import { useRef, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useScrollHint } from "@shared/lib/scrollHint";
import { OUTCOME_VIEWS, type OutcomeView } from "../lib/urlState";
import { useOutcomeModel } from "../model";
import { VIEW_PANEL_ID, viewTabId } from "./modeIds";
import "./modeTabs.css";

/**
 * Вкладки режимов центра: «Результат», «Матрица», «Атлас», «Сравнить» (template-studio-outcome.md,
 * раздел 3.6). Режим живёт в адресе (`view`). Это `tablist` с ручной активацией: стрелки, Home и End
 * двигают фокус, Enter и Space (или клик) открывают режим. Автоматическая активация запускала бы
 * дорогой расчёт атласа (секунды, 6 в минуту) на каждом проходе стрелкой.
 */
export const ModeTabs = () => {
  const { t } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const refs = useRef(new Map<OutcomeView, HTMLButtonElement>());
  const current = url.state.view;
  // Не поместились (телефон, крупный текст): край затухает, выбранный режим не прячется за краем.
  const hintRef = useScrollHint(current);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const at = OUTCOME_VIEWS.indexOf(
      OUTCOME_VIEWS.find((view) => refs.current.get(view) === event.target) ??
        current,
    );
    const last = OUTCOME_VIEWS.length - 1;
    const to =
      event.key === "ArrowRight"
        ? at === last
          ? 0
          : at + 1
        : event.key === "ArrowLeft"
          ? at === 0
            ? last
            : at - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (to === null) return;
    event.preventDefault();
    const next = OUTCOME_VIEWS[to];
    if (next) refs.current.get(next)?.focus();
  };

  return (
    <div
      ref={hintRef}
      className="po-modes scroll-hint"
      role="tablist"
      aria-label={t("modes.tabs.label")}
      onKeyDown={onKeyDown}
      data-testid="outcome-modes"
    >
      {OUTCOME_VIEWS.map((view) => (
        <button
          key={view}
          ref={(node) => {
            if (node) refs.current.set(view, node);
            else refs.current.delete(view);
          }}
          id={viewTabId(view)}
          type="button"
          role="tab"
          className="po-mode-tab"
          aria-selected={current === view}
          aria-controls={VIEW_PANEL_ID}
          tabIndex={current === view ? 0 : -1}
          data-testid={`outcome-view-${view}`}
          onClick={() => {
            if (view !== current) url.update({ view }, true);
          }}
        >
          {t(`modes.tabs.${view}`)}
        </button>
      ))}
    </div>
  );
};
