import type { FormEventHandler, ReactNode } from "react";

export type CloneStepLayoutProps = {
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

// Каркас шага мастера клонирования: содержимое сверху, кнопки внизу под чертой.
// Страница прокручивается целиком, поэтому, в отличие от окна подключения,
// высоту содержимого не ограничиваем.
export const CloneStepLayout = ({
  children,
  start,
  end,
  onSubmit,
  id,
  "aria-label": ariaLabel,
}: CloneStepLayoutProps) => {
  const body = (
    <>
      <div className="flex flex-col" style={{ gap: "1rem" }}>
        {children}
      </div>
      <div
        className="flex items-center"
        style={{
          justifyContent: "space-between",
          gap: "0.625rem",
          paddingTop: "1rem",
          marginTop: "1.25rem",
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
