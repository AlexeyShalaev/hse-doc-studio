import type { FormEventHandler, ReactNode } from "react";

export type StepLayoutProps = {
  children: ReactNode;
  /** Слева внизу: «Отмена», «Назад». */
  start?: ReactNode;
  /** Справа внизу: главное действие шага. */
  end?: ReactNode;
  /** Если задан, шаг становится формой: Enter в поле отправляет её. */
  onSubmit?: FormEventHandler<HTMLFormElement>;
  id?: string;
  "aria-label"?: string;
};

// Каркас шага окна подключения: содержимое прокручивается, а кнопки остаются на
// месте. Один каркас для всех шагов, чтобы окно не прыгало при переходах.
export const StepLayout = ({
  children,
  start,
  end,
  onSubmit,
  id,
  "aria-label": ariaLabel,
}: StepLayoutProps) => {
  const body = (
    <>
      <div
        className="flex flex-col"
        style={{
          gap: 14,
          overflowY: "auto",
          maxHeight: "calc(100vh - 340px)",
          minHeight: 180,
          // Запас под рамку фокуса у полей на краях прокручиваемой области.
          padding: "2px 4px 4px",
          margin: "0 -4px",
        }}
      >
        {children}
      </div>
      <div
        className="flex items-center"
        style={{
          justifyContent: "space-between",
          gap: 10,
          paddingTop: 14,
          marginTop: 14,
          borderTop: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center" style={{ gap: 8 }}>
          {start}
        </div>
        <div className="flex items-center" style={{ gap: 8 }}>
          {end}
        </div>
      </div>
    </>
  );
  if (onSubmit) {
    return (
      <form id={id} aria-label={ariaLabel} onSubmit={onSubmit} noValidate>
        {body}
      </form>
    );
  }
  return (
    <div id={id} role="group" aria-label={ariaLabel}>
      {body}
    </div>
  );
};
