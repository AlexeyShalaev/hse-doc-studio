import type { ReactNode } from "react";

// Тело окна, которое прокручивается, если не помещается на невысоком экране:
// заголовок и кнопки остаются на месте. Отступ в два пикселя не даёт обрезать
// рамку фокуса у крайних элементов.
export const DialogBody = ({ children }: { children: ReactNode }) => (
  <div
    style={{
      maxHeight: "calc(100vh - 16.25rem)",
      overflowY: "auto",
      padding: "0.125rem",
      margin: "-0.125rem",
    }}
  >
    {children}
  </div>
);
