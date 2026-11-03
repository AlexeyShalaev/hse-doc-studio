import type { OnboardingAnswers } from "@entities/onboarding";

export type QuestionId = keyof OnboardingAnswers;

/** Какие вопросы задать: администратору «над чем работаете» не нужен. */
export const questionsFor = (answers: OnboardingAnswers): QuestionId[] =>
  answers.role === "admin"
    ? ["role", "latex", "git"]
    : ["role", "work", "latex", "git"];
