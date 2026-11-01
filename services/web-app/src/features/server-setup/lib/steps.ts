import type {
  RegistrationMode,
  ServerSetupCheck,
  ServerSetupSettings,
  ServerSetupStatus,
} from "@entities/session";
import type { SetupSettingsBody } from "../api/serverSetupApi";

/** Шаги мастера по порядку: язык, админ, регистрация, входы, окружение, готово. */
export const SETUP_STEPS = [
  "language",
  "admin",
  "registration",
  "signin",
  "environment",
  "done",
] as const;
export type SetupStepId = (typeof SETUP_STEPS)[number];

export const nextStep = (step: SetupStepId): SetupStepId =>
  SETUP_STEPS[
    Math.min(SETUP_STEPS.indexOf(step) + 1, SETUP_STEPS.length - 1)
  ] ?? step;

export const prevStep = (step: SetupStepId): SetupStepId =>
  SETUP_STEPS[Math.max(SETUP_STEPS.indexOf(step) - 1, 0)] ?? step;

/**
 * С какого шага продолжить после перезагрузки страницы: по тому, что сервер
 * уже сделал. Админ создан: дальше регистрация; настройки записаны: окружение.
 */
export const resumeStep = (status: ServerSetupStatus): SetupStepId => {
  if (status.steps_done.includes("settings")) return "environment";
  if (status.steps_done.includes("admin")) return "registration";
  return "language";
};

/**
 * Мастер ведёт только администратор. Если админ уже создан, а сессии админа в
 * этой вкладке нет, человек проиграл гонку за первого админа или админ пришёл
 * из окружения: нейтральный экран «установку уже настраивает другой».
 */
export const isOccupied = (
  status: ServerSetupStatus,
  isAdminSession: boolean,
): boolean => status.steps_done.includes("admin") && !isAdminSession;

// Что без чего не работает: база и хранилище обязательны, раннеры придут позже.
export const REQUIRED_CHECKS: readonly ServerSetupCheck["id"][] = [
  "database",
  "storage",
];

export type EnvironmentVerdict = {
  /** Красные обязательные проверки: мастер дальше не пускает. */
  blocking: ServerSetupCheck["id"][];
  /** Не настроено или упало необязательное: предупреждение, не запрет. */
  warnings: ServerSetupCheck["id"][];
};

export const environmentVerdict = (
  checks: readonly ServerSetupCheck[],
): EnvironmentVerdict => {
  const blocking: ServerSetupCheck["id"][] = [];
  const warnings: ServerSetupCheck["id"][] = [];
  for (const check of checks) {
    const required = REQUIRED_CHECKS.includes(check.id);
    if (check.status === "fail" && required) blocking.push(check.id);
    else if (check.status !== "ok") warnings.push(check.id);
  }
  return { blocking, warnings };
};

/** Правка настроек в форме: домены хранятся одной строкой. */
export type SettingsDraft = {
  registration_mode: RegistrationMode;
  domains: string;
  require_approval: boolean;
  password_enabled: boolean;
};

export const draftFromSettings = (
  settings: ServerSetupSettings,
): SettingsDraft => ({
  registration_mode: settings.registration_mode,
  domains: settings.registration_domains.join(", "),
  require_approval: settings.require_approval,
  password_enabled: settings.password_enabled,
});

/** «hse.ru, @edu.hse.ru» -> ["hse.ru", "edu.hse.ru"]: без пустых, @ и повторов. */
export const parseDomains = (text: string): string[] => {
  const seen = new Set<string>();
  for (const raw of text.split(/[\s,;]+/)) {
    const domain = raw.trim().replace(/^@/, "").toLowerCase();
    if (domain !== "") seen.add(domain);
  }
  return [...seen];
};

export const draftIsValid = (draft: SettingsDraft): boolean =>
  draft.registration_mode !== "domains" ||
  parseDomains(draft.domains).length > 0;

export const draftToBody = (draft: SettingsDraft): SetupSettingsBody => ({
  registration_mode: draft.registration_mode,
  registration_domains:
    draft.registration_mode === "domains" ? parseDomains(draft.domains) : [],
  require_approval: draft.require_approval,
  password_enabled: draft.password_enabled,
});
