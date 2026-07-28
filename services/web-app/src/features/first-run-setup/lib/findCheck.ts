import type { SetupStatus } from "@entities/setup";

/** Проверка по идентификатору — по ней экран решает, что показывать. */
export const findCheck = (
  status: SetupStatus | undefined,
  id: string,
): SetupStatus["checks"][number] | undefined =>
  status?.checks.find((check) => check.id === id);
