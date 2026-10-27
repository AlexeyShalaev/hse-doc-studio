import type { ReactNode } from "react";

// Тело окна, которое прокручивается, если не помещается на невысоком экране:
// заголовок и кнопки остаются на месте. Отступ в два пикселя не даёт обрезать
// рамку фокуса у крайних элементов.
export const DialogBody = ({ children }: { children: ReactNode }) => (
  <div
    style={{
      maxHeight: "calc(100vh - 260px)",
      overflowY: "auto",
      padding: 2,
      margin: -2,
    }}
  >
    {children}
  </div>
);
