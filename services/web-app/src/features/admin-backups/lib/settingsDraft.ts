import type { BackupSettings, SettingsBody } from "../api/schemas";

export type SettingsDraft = {
  enabled: boolean;
  scheduleKind: "interval" | "cron";
  intervalHours: string;
  cron: string;
  keepLast: string;
  keepDays: string;
  encryptionMode: "installation" | "passphrase";
  notifyAdmins: boolean;
  passphrase: string;
};

export const settingsDraftOf = (s: BackupSettings): SettingsDraft => ({
  enabled: s.enabled,
  scheduleKind: s.schedule_kind,
  intervalHours: String(s.interval_hours),
  cron: s.cron,
  keepLast: String(s.keep_last),
  keepDays: String(s.keep_days),
  encryptionMode: s.encryption_mode,
  notifyAdmins: s.notify_admins,
  passphrase: "",
});

const CRON_RANGES: readonly (readonly [number, number])[] = [
  [0, 59],
  [0, 23],
  [1, 31],
  [1, 12],
  [0, 7],
];

const cronItemOk = (item: string, low: number, high: number): boolean => {
  const [body = "", step, ...rest] = item.split("/");
  if (rest.length > 0) return false;
  if (step !== undefined && !/^[1-9]\d*$/.test(step)) return false;
  if (body === "*") return true;
  const range = /^(\d+)-(\d+)$/.exec(body);
  if (range) {
    const [from, to] = [Number(range[1]), Number(range[2])];
    return low <= from && from <= to && to <= high;
  }
  return /^\d+$/.test(body) && Number(body) >= low && Number(body) <= high;
};

/** Пять полей cron в UTC; сервер проверяет ещё раз и считает ближайшее срабатывание. */
export const cronProblem = (text: string): boolean => {
  const fields = text.trim().split(/\s+/);
  if (fields.length !== CRON_RANGES.length) return true;
  return !fields.every((field, index) => {
    const [low, high] = CRON_RANGES[index] ?? [0, 0];
    return field.split(",").every((item) => cronItemOk(item, low, high));
  });
};

export type SettingsProblem =
  "interval_hours" | "cron" | "keep_last" | "keep_days" | "passphrase";

const MIN_PASSPHRASE = 12;

const wholeNumber = (text: string, max: number): number | null => {
  if (!/^\d+$/.test(text.trim())) return null;
  const n = Number(text);
  return n <= max ? n : null;
};

/** Тело запроса или поле с ошибкой. */
export const settingsFromDraft = (
  draft: SettingsDraft,
  passphraseSet: boolean,
): { body: SettingsBody } | { problem: SettingsProblem } => {
  const interval = wholeNumber(draft.intervalHours, 24 * 90);
  if (draft.scheduleKind === "interval" && (interval === null || interval < 1))
    return { problem: "interval_hours" };
  if (draft.scheduleKind === "cron" && cronProblem(draft.cron))
    return { problem: "cron" };
  const keepLast = wholeNumber(draft.keepLast, 10_000);
  if (keepLast === null) return { problem: "keep_last" };
  const keepDays = wholeNumber(draft.keepDays, 3650);
  if (keepDays === null) return { problem: "keep_days" };
  const phrase = draft.passphrase;
  if (phrase !== "" && phrase.length < MIN_PASSPHRASE)
    return { problem: "passphrase" };
  if (draft.encryptionMode === "passphrase" && phrase === "" && !passphraseSet)
    return { problem: "passphrase" };
  return {
    body: {
      enabled: draft.enabled,
      schedule_kind: draft.scheduleKind,
      interval_hours: interval ?? 24,
      cron: draft.cron.trim() || "0 3 * * *",
      keep_last: keepLast,
      keep_days: keepDays,
      encryption_mode: draft.encryptionMode,
      notify_admins: draft.notifyAdmins,
      passphrase: phrase === "" ? null : phrase,
    },
  };
};
