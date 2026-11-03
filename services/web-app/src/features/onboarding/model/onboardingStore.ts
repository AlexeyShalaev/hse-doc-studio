import { create } from "zustand";
import type { OnboardingAnswers } from "@entities/onboarding";

/**
 * Где сейчас человек в онбординге (живёт только во вкладке):
 * - intro: приветствие и анкета;
 * - interface: экскурсия по главной;
 * - demo: песочница с демо-проектом (маршрут /onboarding/demo);
 * - finish: итог и предложение создать настоящий проект.
 */
export type OnboardingPhase =
  "idle" | "intro" | "interface" | "demo" | "finish";

/** Откуда начали: сам при первом входе или вручную (меню справки, профиль, приглашение). */
export type OnboardingSource = "auto" | "manual";

type OnboardingStore = {
  phase: OnboardingPhase;
  source: OnboardingSource;
  answers: OnboardingAnswers;
  /** Тур идёт сам, без нажатий (запись роликов для документации). */
  autoplay: boolean;
  start: (source: OnboardingSource, answers?: OnboardingAnswers) => void;
  openDemo: (options?: {
    autoplay?: boolean;
    answers?: OnboardingAnswers;
  }) => void;
  setAnswers: (answers: OnboardingAnswers) => void;
  goTo: (phase: OnboardingPhase) => void;
  close: () => void;
};

export const useOnboardingStore = create<OnboardingStore>((set) => ({
  phase: "idle",
  source: "manual",
  answers: {},
  autoplay: false,
  start: (source, answers) => {
    set((s) => ({
      phase: "intro",
      source,
      answers: answers ?? s.answers,
      autoplay: false,
    }));
  },
  openDemo: (options) => {
    set((s) => ({
      phase: "demo",
      answers: options?.answers ?? s.answers,
      autoplay: options?.autoplay ?? false,
    }));
  },
  setAnswers: (answers) => {
    set({ answers });
  },
  goTo: (phase) => {
    set({ phase });
  },
  close: () => {
    set({ phase: "idle", autoplay: false });
  },
}));
