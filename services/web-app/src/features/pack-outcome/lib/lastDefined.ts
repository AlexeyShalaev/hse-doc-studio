import { useState } from "react";

/**
 * Последнее значение, которое не было пустым. Нужен, чтобы после неудачного пересчёта на экране
 * остался прежний результат (серым), а не пустое место. Обновляется прямо при рендере: так
 * React рекомендует хранить производное состояние без эффекта.
 */
export const useLastDefined = <T>(value: T | undefined): T | undefined => {
  const [kept, setKept] = useState<T | undefined>(value);
  if (value !== undefined && value !== kept) setKept(value);
  return value ?? kept;
};
