import type { OnboardingState } from "@entities/onboarding";
import { SCENARIO_VERSION } from "../model/scenario";

/** Флаг в localStorage: `on` включает автозапуск под автоматизацией (e2e онбординга), `off` выключает всегда. */
export const AUTOSTART_FLAG = "hds.onboarding.autostart";
/** Когда человек закрыл приглашение пройти тур (ISO-время). */
export const INVITE_DISMISSED_KEY = "hds.onboarding.invite-dismissed";

export type AutostartEnv = {
  pathname: string;
  /** navigator.webdriver: браузер под Playwright/Selenium. */
  automated: boolean;
  flag: string | null;
};

export type OnboardingPrompt = "autostart" | "invite" | "none";

const allowedUnderAutomation = (env: AutostartEnv): boolean =>
  env.flag === "on" || (!env.automated && env.flag !== "off");

/**
 * Что показать сейчас: тур сам (новичок на главной), приглашение (давний
 * пользователь или сценарий обновился) или ничего. Под автоматизацией тур и
 * приглашение не всплывают, чтобы не мешать e2e, если флаг не просит обратного.
 */
export const decidePrompt = (
  state: OnboardingState | undefined,
  env: AutostartEnv,
  inviteDismissed: boolean,
): OnboardingPrompt => {
  if (!state || env.pathname !== "/" || !allowedUnderAutomation(env)) {
    return "none";
  }
  if (state.status === "pending") return "autostart";
  if (inviteDismissed) return "none";
  // Давний пользователь или тур брошен на середине (закрыли вкладку): приглашение.
  if (state.status === "suggested" || state.status === "in_progress") {
    return "invite";
  }
  if (
    state.status === "completed" &&
    state.scenario_version < SCENARIO_VERSION
  ) {
    return "invite";
  }
  return "none";
};

export const readAutostartEnv = (pathname: string): AutostartEnv => {
  let flag: string | null;
  try {
    flag = window.localStorage.getItem(AUTOSTART_FLAG);
  } catch {
    flag = null;
  }
  return {
    pathname,
    automated: typeof navigator !== "undefined" && navigator.webdriver,
    flag,
  };
};
