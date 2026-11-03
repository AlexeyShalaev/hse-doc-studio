import { z } from "zod";

export const ONBOARDING_STATUSES = [
  "pending",
  "suggested",
  "in_progress",
  "completed",
  "skipped",
] as const;

export const OnboardingStatusSchema = z.enum(ONBOARDING_STATUSES);
export type OnboardingStatus = z.infer<typeof OnboardingStatusSchema>;

export const OnboardingAnswersSchema = z.object({
  role: z.string().optional(),
  work: z.string().optional(),
  latex: z.string().optional(),
  git: z.string().optional(),
});
export type OnboardingAnswers = z.infer<typeof OnboardingAnswersSchema>;

export const OnboardingStateSchema = z.object({
  // Более новая Студия может прислать незнакомый статус: считаем его «пройден».
  status: z
    .string()
    .transform((value): OnboardingStatus =>
      (ONBOARDING_STATUSES as readonly string[]).includes(value)
        ? (value as OnboardingStatus)
        : "completed",
    ),
  scenario_version: z.number(),
  step: z.string().nullable(),
  answers: OnboardingAnswersSchema,
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  updated_at: z.string().nullable(),
});
export type OnboardingState = z.infer<typeof OnboardingStateSchema>;

export type OnboardingUpdate = {
  status?: Exclude<OnboardingStatus, "suggested">;
  scenario_version?: number;
  /** Пустая строка снимает шаг. */
  step?: string;
  answers?: OnboardingAnswers;
};
