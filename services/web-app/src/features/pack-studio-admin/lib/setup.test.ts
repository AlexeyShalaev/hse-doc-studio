import { describe, expect, it } from "vitest";
import { deriveSetup } from "./setup";

describe("deriveSetup: чек-лист админки Студии", () => {
  it.each([
    // enabled, grants, repos, done, total, status
    [false, 0, 0, 0, 3, "off"],
    [false, 2, 1, 2, 3, "off"],
    [true, 0, 0, 1, 3, "needAccess"],
    [true, 1, 0, 2, 3, "ready"],
    [true, 1, 1, 3, 3, "ready"],
    [true, 0, 2, 2, 3, "needAccess"],
    [true, 1, null, 2, 2, "ready"],
    [false, 0, null, 0, 2, "off"],
  ] as const)(
    "включена %s, доступов %s, репозиториев %s: сделано %s из %s, статус %s",
    (enabled, grants, repos, done, total, status) => {
      const setup = deriveSetup({ enabled, grants, repos });
      expect(setup.done).toBe(done);
      expect(setup.total).toBe(total);
      expect(setup.status).toBe(status);
    },
  );

  it("шаг репозитория есть, только если у установки есть хранилище доступов", () => {
    expect(
      deriveSetup({ enabled: true, grants: 1, repos: 0 }).steps.map(
        (s) => s.id,
      ),
    ).toEqual(["enabled", "access", "repo"]);
    expect(
      deriveSetup({ enabled: true, grants: 1, repos: null }).steps.map(
        (s) => s.id,
      ),
    ).toEqual(["enabled", "access"]);
  });
});
