import { apiClient, parseResp } from "@shared/api";
import {
  OnboardingStateSchema,
  type OnboardingUpdate,
} from "./onboardingSchemas";

// Онбординг не главное: ошибка сохранения шага не должна сыпать тосты поверх тура.
export const onboardingApi = {
  get: () =>
    apiClient
      .get("/onboarding", { silentError: true })
      .then(parseResp(OnboardingStateSchema)),

  update: (body: OnboardingUpdate) =>
    apiClient
      .patch("/onboarding", body, { silentError: true })
      .then(parseResp(OnboardingStateSchema)),

  reset: () =>
    apiClient
      .post("/onboarding/reset", null, { silentError: true })
      .then(parseResp(OnboardingStateSchema)),
};
