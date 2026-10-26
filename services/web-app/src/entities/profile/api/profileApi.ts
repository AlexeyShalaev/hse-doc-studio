import { ApiError, apiClient, parseResp } from "@shared/api";
import {
  ProfileSchema,
  ProfileValidationErrorSchema,
  type ProfileRequest,
  type ProfileValidationError,
} from "./profileSchemas";

// 422 на PUT /profile: FastAPI отдаёт список {loc, code, msg}. Общий перехватчик
// axios кладёт его в ApiError.data как есть, поэтому разбираем и поднимаем свою
// ошибку: форма показывает сообщения у полей по loc и code.
export class ProfileValidationFailed extends Error {
  readonly issues: ProfileValidationError["detail"];

  constructor(issues: ProfileValidationError["detail"]) {
    super("profile validation failed");
    this.name = "ProfileValidationFailed";
    this.issues = issues;
  }
}

const toValidationFailure = (error: unknown): unknown => {
  if (error instanceof ApiError && error.status === 422) {
    const parsed = ProfileValidationErrorSchema.safeParse({
      detail: error.data,
    });
    if (parsed.success) return new ProfileValidationFailed(parsed.data.detail);
  }
  return error;
};

export const profileApi = {
  get: () => apiClient.get("/profile").then(parseResp(ProfileSchema)),

  update: (params: ProfileRequest) =>
    apiClient
      // Ошибки проверки показывает форма у полей, а не тост.
      .put("/profile", params, { silentError: true })
      .then(parseResp(ProfileSchema))
      .catch((error: unknown) => {
        throw toValidationFailure(error);
      }),

  clear: () => apiClient.delete("/profile").then(parseResp(ProfileSchema)),
};
