import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBootstrap } from "@entities/session";
import {
  onboardingApi,
  onboardingKeys,
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

// Сохранения идут строго по очереди: сервер читает состояние и пишет его целиком,
// и два одновременных PATCH (ответы анкеты и первый шаг тура) затирали бы друг друга.
let queue: Promise<unknown> = Promise.resolve();

/**
 * Сохранить прогресс. Ошибка сохранения не мешает туру: он идёт дальше, а
 * состояние догонит следующим шагом.
 */
export const useOnboardingProgress = () => {
  const queryClient = useQueryClient();
  const available = useOnboardingAvailable();
  return useCallback(
    (patch: OnboardingUpdate) => {
      if (!available) return;
      const body = { scenario_version: SCENARIO_VERSION, ...patch };
      queue = queue
        .catch(() => undefined)
        .then(() => onboardingApi.update(body))
        .then((state) => {
          queryClient.setQueryData(onboardingKeys.state(), state);
        })
        .catch(() => undefined);
    },
    [queryClient, available],
  );
};
