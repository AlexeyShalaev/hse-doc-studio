import { describe, expect, it } from "vitest";
import { safeNextPath } from "./safeNextPath";

describe("safeNextPath", () => {
  it.each([
    "/",
    "/projects/p1",
    "/projects/p1/documents/d1?tab=files#top",
    "/settings/appearance",
  ])("keeps the in-app path %s", (path) => {
    expect(safeNextPath(path)).toBe(path);
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["empty", ""],
    ["no leading slash", "projects"],
    ["absolute url", "https://evil.example/x"],
    ["scheme-relative", "//evil.example"],
    ["triple slash", "///evil.example"],
    ["backslash", "/\\evil.example"],
    ["slash backslash", "/\\/evil.example"],
    ["tab inside", "/\t/evil.example"],
    ["newline inside", "/\n/evil.example"],
    ["space", "/ /evil.example"],
    ["encoded slash", "/%2F/evil.example"],
    ["encoded backslash", "/%5Cevil.example"],
    ["encoded tab", "/%09/evil.example"],
    ["broken encoding", "/%E0%A4%A"],
    ["javascript scheme", "javascript:alert(1)"],
    ["data scheme", "data:text/html,x"],
    ["login loop", "/login"],
    ["login loop in other case", "/Login?x=1"],
    ["auth in upper case", "/AUTH/oidc/callback"],
    ["login with query", "/login?next=/"],
    ["auth endpoint", "/auth/oidc/callback"],
    ["api", "/api/v1/projects"],
    ["too long", `/${"a".repeat(3000)}`],
  ])("rejects %s", (_name, value) => {
    expect(safeNextPath(value)).toBe("/");
  });

  it("uses the given fallback", () => {
    expect(safeNextPath("//evil", "/projects")).toBe("/projects");
  });

  it("does not treat a longer name as a blocked prefix", () => {
    expect(safeNextPath("/login-help")).toBe("/login-help");
    expect(safeNextPath("/apiary")).toBe("/apiary");
  });
});
