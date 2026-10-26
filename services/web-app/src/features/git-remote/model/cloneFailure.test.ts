import { describe, expect, it } from "vitest";
import { cloneFailureTarget, isBundleCode } from "./cloneFailure";

describe("cloneFailureTarget", () => {
  it.each([
    ["profile_required", "profile"],
    ["folder_not_empty", "folder"],
    ["project_exists", "folder"],
    ["auth_failed", "source"],
    ["host_key_changed", "source"],
    ["offline", "source"],
    ["not_found_or_no_access", "source"],
    ["bundle_invalid", "source"],
    ["bundle_password_wrong", "source"],
    ["git_error", "general"],
    ["something_new", "general"],
  ])("%s ведёт к %s", (code, target) => {
    expect(cloneFailureTarget(code)).toBe(target);
  });

  it("ошибки файла отличает от ошибок адреса", () => {
    expect(isBundleCode("bundle_password_required")).toBe(true);
    expect(isBundleCode("bundle_prerequisites_missing")).toBe(true);
    expect(isBundleCode("auth_failed")).toBe(false);
  });
});
