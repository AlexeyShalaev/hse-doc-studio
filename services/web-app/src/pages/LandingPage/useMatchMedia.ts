import { useMediaQuery } from "@shared/lib";

/** Совпадает ли запрос с окном; верный с первого кадра, обновляется при изменении размера. */
export const useMatchMedia = (query: string): boolean => useMediaQuery(query);
