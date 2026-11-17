import { useTranslation } from "react-i18next";
import type { PhoneNav } from "../../lib/phoneNav";
import type { OutcomeTab } from "../../lib/urlState";

type PhoneTabsProps = {
  nav: PhoneNav;
  /** Сколько вводных отличается от умолчаний. */
  changedInputs: number;
  /** Выбран элемент результата: у вкладки «Почему?» метка. */
  hasSelection: boolean;
  /** В режиме «Как студент» вкладки «Почему?» нет. */
  student: boolean;
};

/**
 * Нижние вкладки телефона: «Вводные» (лист), «Результат» и «Почему?» (страницы). Счётчики:
 * число изменённых вводных и метка выбранного элемента. Это навигация с `aria-current`, а не
 * `tablist`: у «Вводных» нет своей панели, это окно поверх страницы.
 */
export const PhoneTabs = ({
  nav,
  changedInputs,
  hasSelection,
  student,
}: PhoneTabsProps) => {
  const { t } = useTranslation("packOutcome");
  const tabs: readonly OutcomeTab[] = student
    ? ["inputs", "result"]
    : ["inputs", "result", "rules"];
  return (
    <nav
      className="po-tabs"
      aria-label={t("phone.tabs")}
      data-testid="outcome-tabs"
    >
      {tabs.map((tab) => {
        const badge =
          tab === "inputs"
            ? changedInputs
            : tab === "rules" && hasSelection
              ? 1
              : 0;
        const sheet = tab === "inputs";
        const current = sheet
          ? nav.tab === "inputs"
          : nav.main === tab && nav.tab !== "inputs";
        const detail =
          tab === "inputs" && badge > 0
            ? t("phone.changed", { count: badge })
            : tab === "rules" && badge > 0
              ? t("phone.selected")
              : "";
        const name = t(`phone.${tab}`);
        return (
          <button
            key={tab}
            type="button"
            className="po-tab"
            data-active={current ? "true" : undefined}
            aria-current={!sheet && current ? "page" : undefined}
            aria-haspopup={sheet ? "dialog" : undefined}
            aria-expanded={sheet ? current : undefined}
            aria-label={detail === "" ? undefined : `${name}, ${detail}`}
            data-testid={`outcome-tab-${tab}`}
            onClick={() => {
              nav.go(tab);
            }}
          >
            <span>{name}</span>
            {badge > 0 && (
              <span
                className="po-badge"
                aria-hidden="true"
                data-testid={`outcome-tab-${tab}-badge`}
              >
                {tab === "rules" ? "" : badge}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
};
