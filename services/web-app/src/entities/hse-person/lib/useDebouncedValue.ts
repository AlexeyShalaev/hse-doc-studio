import { useEffect, useState } from "react";

/**
 * Returns `value` delayed by `delayMs`. Used to throttle the search input so a
 * request is issued only after the user pauses typing (politeness towards the
 * upstream HSE directory, which the backend rate-limits further).
 */
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
