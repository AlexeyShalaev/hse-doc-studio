import type { PackStudioGrant } from "@entities/pack-studio";

/** Шаги настройки раздела: включить, выдать доступ, подключить репозиторий. */
export type SetupStepId = "enabled" | "access" | "repo";

export type SetupStep = { id: SetupStepId; done: boolean };

/** Одна метка состояния страницы: «раздел работает», «раздел выключен» или «осталось выдать доступ». */
export type SetupStatus = "ready" | "off" | "needAccess";

export type SetupInput = {
  enabled: boolean;
  grants: number;
  /**
   * Сколько репозиториев подключено. `null`: хранилища служебных доступов у
   * этой установки нет (локальная Студия), шага нет.
   */
  repos: number | null;
};

export type SetupState = {
  steps: SetupStep[];
  /** Сколько шагов сделано. */
  done: number;
  total: number;
  status: SetupStatus;
};

/**
 * Состояние настройки раздела по трём признакам. Репозиторий шагом считается,
 * но раздел работает и без него: он необязателен, а администратор имеет доступ
 * всегда. Статус выключенного раздела важнее статуса доступа.
 */
export const deriveSetup = (input: SetupInput): SetupState => {
  const steps: SetupStep[] = [
    { id: "enabled", done: input.enabled },
    { id: "access", done: input.grants > 0 },
  ];
  if (input.repos !== null) {
    steps.push({ id: "repo", done: input.repos > 0 });
  }
  const status: SetupStatus = !input.enabled
    ? "off"
    : input.grants > 0
      ? "ready"
      : "needAccess";
  return {
    steps,
    done: steps.filter((s) => s.done).length,
    total: steps.length,
    status,
  };
};

/** Не больше стольких имён в строке «кто может править»: дальше «и ещё N». */
export const MAX_NAMES = 3;

/** Имя в строке «кто может»: человек как есть, группа с подписью. */
export const grantName = (
  grant: PackStudioGrant,
  groupLabel: (name: string) => string,
): string => {
  const name = grant.name ?? grant.subject_id;
  return grant.subject === "group" ? groupLabel(name) : name;
};
