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
          gap: "0.875rem",
          overflowY: "auto",
          maxHeight: "calc(100vh - 21.25rem)",
          minHeight: "11.25rem",
          // Запас под рамку фокуса у полей на краях прокручиваемой области.
          padding: "0.125rem 0.25rem 0.25rem",
          margin: "0 -0.25rem",
        }}
      >
        {children}
      </div>
      <div
        className="flex items-center"
        style={{
          justifyContent: "space-between",
          gap: "0.625rem",
          paddingTop: "0.875rem",
          marginTop: "0.875rem",
          borderTop: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          {start}
        </div>
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
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
