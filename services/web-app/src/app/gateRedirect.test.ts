import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BootstrapSchema, LOCAL_BOOTSTRAP } from "@entities/session";
import {
  isPublicPath,
  resolveGateRedirect,
  showsLanding,
} from "./gateRedirect";

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

  const landingOff = { ...anon, landing: { enabled: false, name: "HSE" } };

  it("uses a bare /login for the home page when the landing is switched off", () => {
    expect(resolveGateRedirect(landingOff, at("/"))).toBe("/login");
    expect(resolveGateRedirect({ ...anon, landing: null }, at("/"))).toBe(
      "/login",
    );
    expect(resolveGateRedirect({ ...anon, landing: undefined }, at("/"))).toBe(
      "/login",
    );
  });

  it("keeps an anonymous visitor on the home page when the landing is on", () => {
    expect(resolveGateRedirect(anon, at("/"))).toBeNull();
    expect(
      resolveGateRedirect(anon, at("/", "?next=%2Fprojects%2Fa")),
    ).toBeNull();
    expect(showsLanding(anon, "/")).toBe(true);
  });

  it("shows the landing only on the root of a ready server installation for an anonymous visitor", () => {
    expect(showsLanding(anon, "/projects/x")).toBe(false);
    expect(showsLanding(anon, "/login")).toBe(false);
    expect(showsLanding(landingOff, "/")).toBe(false);
    expect(showsLanding(fixture("server_user"), "/")).toBe(false);
    expect(showsLanding(fixture("server_admin"), "/")).toBe(false);
    expect(showsLanding(fixture("guest"), "/")).toBe(false);
    expect(showsLanding(fixture("server_needs_admin"), "/")).toBe(false);
    expect(showsLanding(LOCAL_BOOTSTRAP, "/")).toBe(false);
    expect(showsLanding(fixture("local"), "/")).toBe(false);
  });

  it("keeps every other link of an anonymous visitor as before when the landing is on", () => {
    expect(
      resolveGateRedirect(anon, at("/login", "?next=%2Fprojects%2Fa")),
    ).toBeNull();
    expect(resolveGateRedirect(anon, at("/invite/abc"))).toBeNull();
    expect(resolveGateRedirect(anon, at("/reset/t"))).toBeNull();
    expect(resolveGateRedirect(anon, at("/verify/t"))).toBeNull();
    expect(resolveGateRedirect(anon, at("/s/token"))).toBeNull();
    expect(resolveGateRedirect(anon, at("/project-invite/t"))).toBeNull();
    expect(
      resolveGateRedirect(anon, at("/settings/runners/pair", "?code=ABCD")),
    ).toBe(
      `/login?next=${encodeURIComponent("/settings/runners/pair?code=ABCD")}`,
    );
    expect(resolveGateRedirect(anon, at("/local-studio"))).toBe(
      `/login?next=${encodeURIComponent("/local-studio")}`,
    );
  });

  it("does not change the home page of a signed-in user", () => {
    expect(resolveGateRedirect(fixture("server_user"), at("/"))).toBeNull();
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
