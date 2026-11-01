import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BootstrapSchema, LOCAL_BOOTSTRAP } from "@entities/session";
import { isPublicPath, resolveGateRedirect } from "./gateRedirect";

const fixture = (name: string) =>
  BootstrapSchema.parse(
    JSON.parse(
      readFileSync(
        join(
          import.meta.dirname,
          "../../../..",
          "contracts/server/fixtures/Bootstrap",
          `${name}.json`,
        ),
        "utf8",
      ),
    ),
  );

const at = (pathname: string, search = "", hash = "") => ({
  pathname,
  search,
  hash,
});

describe("resolveGateRedirect", () => {
  const anon = fixture("server_anonymous");
  const needsAdmin = fixture("server_needs_admin");
  const user = fixture("server_user");

  it("sends an anonymous visitor to /login keeping the target in ?next=", () => {
    expect(resolveGateRedirect(anon, at("/projects/x", "?tab=1", "#a"))).toBe(
      `/login?next=${encodeURIComponent("/projects/x?tab=1#a")}`,
    );
  });

  it("uses a bare /login for the home page", () => {
    expect(resolveGateRedirect(anon, at("/"))).toBe("/login");
  });

  it("lets an anonymous visitor open public screens", () => {
    for (const p of [
      "/login",
      "/register",
      "/forgot",
      "/invite/abc",
      "/reset/t",
      "/verify/t",
      "/auth/error",
    ]) {
      expect(resolveGateRedirect(anon, at(p))).toBeNull();
    }
  });

  it("сравнивает адреса без учёта регистра, как роутер", () => {
    expect(resolveGateRedirect(anon, at("/Login"))).toBeNull();
    expect(isPublicPath("/FORGOT")).toBe(true);
    expect(resolveGateRedirect(user, at("/Login", "?next=%2FLogin"))).toBe("/");
    expect(resolveGateRedirect(user, at("/REGISTER"))).toBe("/");
  });

  it("closes /first-run once the instance is set up", () => {
    expect(resolveGateRedirect(anon, at("/first-run"))).toMatch(/^\/login/);
    expect(resolveGateRedirect(user, at("/first-run"))).toBe("/");
  });

  it("sends everything to /first-run while the wizard is pending", () => {
    expect(resolveGateRedirect(needsAdmin, at("/projects/x"))).toBe(
      "/first-run",
    );
    expect(resolveGateRedirect(needsAdmin, at("/login"))).toBe("/first-run");
    expect(resolveGateRedirect(needsAdmin, at("/first-run"))).toBeNull();
  });

  it("sends a signed-in user away from guest screens, honouring a safe next", () => {
    expect(resolveGateRedirect(user, at("/login"))).toBe("/");
    expect(
      resolveGateRedirect(user, at("/login", "?next=%2Fprojects%2Fa")),
    ).toBe("/projects/a");
    expect(
      resolveGateRedirect(user, at("/login", "?next=%2F%2Fevil.com")),
    ).toBe("/");
    expect(
      resolveGateRedirect(user, at("/login", "?next=https://evil.com")),
    ).toBe("/");
  });

  it("leaves a signed-in user on ordinary pages", () => {
    expect(resolveGateRedirect(user, at("/projects/x"))).toBeNull();
  });

  it("does not redirect anything in local mode except sign-in screens", () => {
    expect(resolveGateRedirect(LOCAL_BOOTSTRAP, at("/projects/x"))).toBeNull();
    expect(resolveGateRedirect(LOCAL_BOOTSTRAP, at("/"))).toBeNull();
    expect(resolveGateRedirect(LOCAL_BOOTSTRAP, at("/login"))).toBe("/");
  });
});

describe("isPublicPath", () => {
  it("ignores a trailing slash and rejects lookalikes", () => {
    expect(isPublicPath("/login/")).toBe(true);
    expect(isPublicPath("/loginx")).toBe(false);
    expect(isPublicPath("/projects/login")).toBe(false);
  });
});
