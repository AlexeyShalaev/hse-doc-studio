import { describe, expect, it } from "vitest";
import type { CatalogSource } from "@entities/pack-catalog";
import { needsAttention, sourceStatus } from "./sourceStatus";

const base = {
  busy: false,
  error: null,
  enabled: true,
  applied_revision: "4b825dc6",
  checked_at: "2026-11-14T09:30:00Z",
  check_ok: true,
  pending_versions: 0,
} as unknown as CatalogSource;
const make = (patch: Partial<CatalogSource>): CatalogSource => ({
  ...base,
  ...patch,
});

describe("sourceStatus: слово о состоянии источника", () => {
  it.each([
    ["всё подключено", {}, "ok", false],
    [
      "идёт проверка важнее всего",
      { busy: true, error: { code: "x", detail: "y" } },
      "busy",
      false,
    ],
    ["ошибка проверки", { error: { code: "x", detail: "y" } }, "failed", true],
    ["выключен", { enabled: false }, "off", false],
    [
      "выключен и не подключался: сначала выключен",
      { enabled: false, applied_revision: null },
      "off",
      false,
    ],
    [
      "ещё не подключался",
      { applied_revision: null, checked_at: null, check_ok: null },
      "new",
      true,
    ],
    ["проверка нашла препятствия", { check_ok: false }, "blocked", true],
    ["есть новые версии", { pending_versions: 2 }, "update", true],
    [
      "препятствия важнее новых версий",
      { check_ok: false, pending_versions: 2 },
      "blocked",
      true,
    ],
  ] as const)("%s", (_name, patch, status, attention) => {
    const s = sourceStatus(make(patch));
    expect(s).toBe(status);
    expect(needsAttention(s)).toBe(attention);
  });
});
