import { z } from "zod";

// Люди, которые сейчас в проекте (docs/design/connected-devices.md, раздел 15): веб-вкладки и локальные Студии
// одним списком. Только место на уровне документа проекта; ни путей, ни позиций курсора, ни деталей машины.

/** Что вкладка вправе сообщить о себе; `local` сервер выводит сам из сигнала Студии. */
export const REPORTED_ACTIVITY = [
  "editing",
  "viewing",
  "reviewing",
  "building",
  "browsing",
] as const;
export type ReportedActivity = (typeof REPORTED_ACTIVITY)[number];

export const PEOPLE_ACTIVITY = [...REPORTED_ACTIVITY, "local"] as const;
export const PeopleActivitySchema = z.enum(PEOPLE_ACTIVITY);
export type PeopleActivity = z.infer<typeof PeopleActivitySchema>;

export const PersonOnlineSchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
  initials: z.string(),
  /** Тот же цвет, что у курсора человека в документе. */
  color: z.string(),
  role: z.enum(["reader", "reviewer", "editor", "owner"]),
  me: z.boolean(),
  activity: PeopleActivitySchema,
  doc_id: z.string().nullable(),
  channels: z.array(z.enum(["web", "studio"])),
  seen_at: z.string(),
});
export type PersonOnline = z.infer<typeof PersonOnlineSchema>;

export const ProjectPeopleSchema = z.strictObject({
  interval_s: z.number().int(),
  online_window_s: z.number().int(),
  total: z.number().int(),
  people: z.array(PersonOnlineSchema),
});
export type ProjectPeople = z.infer<typeof ProjectPeopleSchema>;

/** Сигнал вкладки: где она сейчас. */
export type PresenceSignal = {
  session_id: string;
  activity: ReportedActivity;
  doc_id: string | null;
};
