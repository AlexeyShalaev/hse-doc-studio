import { useEffect, useState } from "react";

// Значение с задержкой: поле ввода обновляется сразу, а запрос по нему уходит,
// когда человек сделал паузу.
export const useDebouncedValue = <T>(value: T, delayMs: number): T => {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const handle = setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      clearTimeout(handle);
    };
  }, [value, delayMs]);

  return debounced;
};
