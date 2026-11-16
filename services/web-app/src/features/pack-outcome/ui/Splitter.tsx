import type { PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import type { PaneResize } from "@shared/lib";

type SplitterProps = {
  resize: PaneResize;
  min: number;
  max: number;
  /** Название панели, которую двигает граница: попадает в подпись. */
  name: string;
  testId: string;
};

/**
 * Граница между колонками. Тянется мышью и пальцем, а с клавиатуры стрелками (шаг 16 px),
 * Home и End ставят предел; для тех, кому перетаскивание недоступно, в шапке панели есть
 * кнопки «Шире» и «Уже» (WCAG 2.5.7).
 */
export const Splitter = ({ resize, min, max, name, testId }: SplitterProps) => {
  const { t } = useTranslation("packOutcome");
  const label = t("panels.resize", { name });
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-description={t("panels.resizeHint")}
      aria-valuenow={Math.round(resize.width)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title={label}
      className="split-resize-handle"
      data-resizing={resize.isResizing ? "true" : undefined}
      data-testid={testId}
      onDoubleClick={resize.reset}
      onPointerDown={(event: PointerEvent<HTMLDivElement>) => {
        resize.startResize(event);
      }}
      onKeyDown={(event) => {
        const step = 16;
        const toward =
          event.key === "ArrowRight"
            ? step
            : event.key === "ArrowLeft"
              ? -step
              : 0;
        if (toward !== 0) {
          event.preventDefault();
          resize.nudge(toward);
        } else if (event.key === "Home") {
          event.preventDefault();
          resize.setWidth(min);
        } else if (event.key === "End") {
          event.preventDefault();
          resize.setWidth(max);
        }
      }}
    />
  );
};
