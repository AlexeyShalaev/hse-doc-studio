import { forwardRef, type ReactNode } from "react";
import {
  ChevronsLeft,
  ChevronsRight,
  PanelLeftClose,
  PanelRightClose,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { PANEL_STEP } from "../lib/panels";

type PanelShellProps = {
  side: "left" | "right";
  title: string;
  /** Подпись области: по умолчанию заголовок панели. */
  label?: string;
  testId: string;
  /** Ширина, px; без неё панель занимает всё место (лист на телефоне). */
  width?: number;
  /** Кнопки «Свернуть», «Шире» и «Уже»; на листе их нет. */
  controls?: {
    collapse: () => void;
    nudge: (delta: number) => void;
  };
  children: ReactNode;
};

/**
 * Боковая панель экрана «Результат»: область-ориентир с подписью, заголовок и кнопки свёртывания
 * и ширины. Фокус на неё переводит F6 (поэтому tabIndex -1).
 */
export const PanelShell = forwardRef<HTMLElement, PanelShellProps>(
  ({ side, title, label, testId, width, controls, children }, ref) => {
    const { t } = useTranslation("packOutcome");
    const Collapse = side === "left" ? PanelLeftClose : PanelRightClose;
    const Wider = side === "left" ? ChevronsRight : ChevronsLeft;
    const Narrower = side === "left" ? ChevronsLeft : ChevronsRight;
    // У левой панели «шире» это вправо, у правой влево: знак шага задаёт сторона границы.
    const sign = side === "left" ? 1 : -1;
    return (
      <section
        ref={ref}
        tabIndex={-1}
        aria-label={label ?? title}
        className="po-panel"
        data-side={side}
        data-testid={testId}
        style={width ? { width: `${String(width / 16)}rem` } : undefined}
      >
        <header className="po-panel-head">
          <h2 className="po-panel-title">{title}</h2>
          {controls && (
            <div className="po-panel-tools">
              <button
                type="button"
                className="icon-btn sm"
                aria-label={`${t("panels.narrower")}: ${title}`}
                title={t("panels.narrower")}
                data-testid={`${testId}-narrower`}
                onClick={() => {
                  controls.nudge(-PANEL_STEP * sign);
                }}
              >
                <Narrower size="0.875rem" aria-hidden="true" />
              </button>
              <button
                type="button"
                className="icon-btn sm"
                aria-label={`${t("panels.wider")}: ${title}`}
                title={t("panels.wider")}
                data-testid={`${testId}-wider`}
                onClick={() => {
                  controls.nudge(PANEL_STEP * sign);
                }}
              >
                <Wider size="0.875rem" aria-hidden="true" />
              </button>
              <button
                type="button"
                className="icon-btn sm"
                aria-label={t("panels.collapse", { name: title })}
                title={t("panels.collapse", { name: title })}
                data-testid={`${testId}-collapse`}
                onClick={controls.collapse}
              >
                <Collapse size="0.875rem" aria-hidden="true" />
              </button>
            </div>
          )}
        </header>
        <div className="po-panel-body">{children}</div>
      </section>
    );
  },
);
PanelShell.displayName = "PanelShell";
