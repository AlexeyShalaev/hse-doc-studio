import { useEffect, useState } from "react";

const matches = (query: string): boolean =>
  typeof window.matchMedia === "function" && window.matchMedia(query).matches;

/** Совпадает ли запрос с окном; обновляется при изменении размера. */
export const useMatchMedia = (query: string): boolean => {
  const [value, setValue] = useState(() => matches(query));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const update = () => {
      setValue(list.matches);
    };
    update();
    list.addEventListener("change", update);
    return () => {
      list.removeEventListener("change", update);
    };
  }, [query]);
  return value;
};
