import type { UpdateSettings } from "../api/schemas";

/** Поля формы: время окна текстом `HH:MM` (UTC), длительность в часах. */
export type SettingsDraft = {
  policy: UpdateSettings["policy"];
  maxBump: UpdateSettings["max_bump"];
  days: number[];
  start: string;
  hours: string;
  backupFirst: boolean;
  verify: UpdateSettings["verify"];
  notifyAdmins: boolean;
};

export type SettingsProblem =
  "window_days" | "window_start_min" | "window_minutes";

export const timeOf = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};

export const minutesOf = (time: string): number | null => {
  const match = /^(\d{1,2}):(\d{2})$/.exec(time.trim());
  if (!match) return null;
  const total = Number(match[1]) * 60 + Number(match[2]);
  return Number(match[1]) < 24 && Number(match[2]) < 60 ? total : null;
};

export const settingsDraftOf = (s: UpdateSettings): SettingsDraft => ({
  policy: s.policy,
  maxBump: s.max_bump,
  days: [...s.window_days].sort(),
  start: timeOf(s.window_start_min),
  hours: String(s.window_minutes / 60),
  backupFirst: s.backup_first,
  verify: s.verify,
  notifyAdmins: s.notify_admins,
});

export const settingsFromDraft = (
  d: SettingsDraft,
): { body: UpdateSettings } | { problem: SettingsProblem } => {
  if (d.days.length === 0) return { problem: "window_days" };
  const start = minutesOf(d.start);
  if (start === null) return { problem: "window_start_min" };
  const hours = Number(d.hours.replace(",", "."));
  const minutes = Math.round(hours * 60);
  if (!Number.isFinite(hours) || minutes < 15 || minutes > 1440)
    return { problem: "window_minutes" };
  return {
    body: {
      policy: d.policy,
      channel: "stable",
      max_bump: d.maxBump,
      window_days: [...d.days].sort(),
      window_start_min: start,
      window_minutes: minutes,
      backup_first: d.backupFirst,
      verify: d.verify,
      notify_admins: d.notifyAdmins,
    },
  };
};
