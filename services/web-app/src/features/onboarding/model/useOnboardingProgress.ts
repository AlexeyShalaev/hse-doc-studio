import { useCallback } from "react";
import { useBootstrap } from "@entities/session";
import {
  useUpdateOnboarding,
  type OnboardingUpdate,
} from "@entities/onboarding";
import { SCENARIO_VERSION } from "./scenario";

/** Есть ли у человека состояние онбординга: локально всегда, на сервере только у вошедшего. */
export const useOnboardingAvailable = (): boolean => {
  const { data } = useBootstrap();
  if (!data) return false;
  if (data.mode === "local") return true;
  return data.user !== null && data.guest === null;
};

/**
 * Сохранить прогресс. Ошибка сохранения не мешает туру: он идёт дальше, а
 * состояние догонит следующим шагом.
 */
export const useOnboardingProgress = () => {
  const { mutate } = useUpdateOnboarding();
  const available = useOnboardingAvailable();
  return useCallback(
    (patch: OnboardingUpdate) => {
      if (!available) return;
      mutate({ scenario_version: SCENARIO_VERSION, ...patch });
    },
    [mutate, available],
  );
};
