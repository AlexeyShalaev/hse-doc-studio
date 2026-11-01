import type { AdminSettingState } from "@entities/session";

/** Ключ закрыт окружением. Ключ, которого нет в ответе, считается свободным. */
export const isLocked = (
  fields: Record<string, AdminSettingState>,
  key: string,
): boolean => fields[key]?.locked ?? false;
