import { useEffect, useRef } from "react";

// Окно меняет кнопки внизу по ходу дела (отправка, слияние, готово). Кнопка, на
// которой стоял фокус, исчезает, и фокус падал бы на саму рамку окна. Поэтому при
// смене шага переносим его на главную кнопку нового шага.
export const useFocusFooter = (step: string) => {
  const ref = useRef<HTMLDivElement>(null);
  const previous = useRef(step);
  useEffect(() => {
    if (previous.current === step) return;
    previous.current = step;
    ref.current
      ?.querySelector<HTMLElement>(
        "button.primary:not(:disabled), button:not(:disabled)",
      )
      ?.focus();
  }, [step]);
  return ref;
};
