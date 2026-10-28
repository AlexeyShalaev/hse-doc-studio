import type { SetupSettingKey } from "@entities/session";

/** Ключ настройки задан окружением: на экране он только для чтения. */
export const isLocked = (
  locked: readonly SetupSettingKey[],
  key: SetupSettingKey,
): boolean => locked.includes(key);
