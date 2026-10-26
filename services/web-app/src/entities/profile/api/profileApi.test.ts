import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { ProfileValidationFailed, profileApi } from "./profileApi";

describe("profileApi.update", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("turns the FastAPI 422 list into per-field issues", async () => {
    const issues = [
      { loc: ["body", "email"], code: "invalid_email", msg: "bad" },
    ];
    vi.spyOn(apiClient, "put").mockRejectedValue(
      new ApiError(
        "Unprocessable",
        "unknown_error",
        422,
        issues as unknown as Record<string, unknown>,
      ),
    );
    const error = await profileApi
      .update({ name: "Иван", email: "x" })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ProfileValidationFailed);
    expect((error as ProfileValidationFailed).issues).toEqual(issues);
  });

  it("keeps other failures as they are", async () => {
    const failure = new ApiError("boom", "git_error", 500);
    vi.spyOn(apiClient, "put").mockRejectedValue(failure);
    await expect(
      profileApi.update({ name: "Иван", email: "a@b.ru" }),
    ).rejects.toBe(failure);
  });

  it("sends the request silently so the form owns the message", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({
      data: {
        name: "Иван",
        email: "a@b.ru",
        effective_name: "Иван",
        effective_email: "a@b.ru",
        is_default: false,
        commit_preview: "Иван <a@b.ru>",
      },
    });
    await profileApi.update({ name: "Иван", email: "a@b.ru" });
    expect(put).toHaveBeenCalledWith(
      "/profile",
      { name: "Иван", email: "a@b.ru" },
      { silentError: true },
    );
  });
});
