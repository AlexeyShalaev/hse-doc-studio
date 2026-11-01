import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BootstrapSchema } from "@entities/session";
import { isPublicPath, resolveGateRedirect } from "./gateRedirect";

// links: гость по ссылке ходит только по своим проектам и главной; страница ссылки открыта всем.

const guest = BootstrapSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../..",
        "contracts/server/fixtures/Bootstrap/guest.json",
      ),
      "utf8",
    ),
  ),
);
const at = (pathname: string) => ({ pathname, search: "", hash: "" });

describe("шлюз: гость по ссылке", () => {
  it("страница ссылки публичная", () => {
    expect(isPublicPath("/s/hsl_abc")).toBe(true);
  });

  it.each([
    "/",
    "/projects/p1",
    "/projects/p1/view",
    "/projects/p1/documents/vkr",
    "/s/hsl_x",
  ])("%s открыт гостю", (path) => {
    expect(resolveGateRedirect(guest, at(path))).toBeNull();
  });

  it.each([
    "/settings",
    "/settings/account",
    "/admin",
    "/admin/users",
    "/wizard",
    "/inbox",
  ])("%s закрыт гостю и ведёт на главную", (path) => {
    expect(resolveGateRedirect(guest, at(path))).toBe("/");
  });
});
