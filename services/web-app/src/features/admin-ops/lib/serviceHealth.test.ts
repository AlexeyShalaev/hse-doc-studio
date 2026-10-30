import { describe, expect, it } from "vitest";
import type { AdminService, AdminStorage } from "@entities/session";
import { serviceHealth, summarizeHealth } from "./serviceHealth";
import { diskTone } from "./storage";

const svc = (over: Partial<AdminService>): AdminService => ({
  id: over.kind ?? "database",
  kind: "database",
  status: "ok",
  detail: null,
  online: null,
  total: null,
  ...over,
});

describe("serviceHealth", () => {
  it("меньше половины раннеров в сети: перебои, хотя сервер говорит ok", () => {
    expect(
      serviceHealth(
        svc({ kind: "runners", status: "ok", online: 2, total: 5 }),
      ),
    ).toBe("partial");
    expect(
      serviceHealth(
        svc({ kind: "runners", status: "ok", online: 3, total: 5 }),
      ),
    ).toBe("ok");
  });

  it("сводка считает частичную работу перебоями, а не нормой", () => {
    const sum = summarizeHealth([
      svc({ kind: "database" }),
      svc({ kind: "runners", online: 1, total: 4 }),
      svc({ kind: "smtp", status: "unconfigured" }),
      svc({ kind: "storage", status: "down" }),
    ]);
    expect(sum.ok.map((s) => s.kind)).toEqual(["database"]);
    expect(sum.warn.map((s) => s.kind)).toEqual(["runners"]);
    expect(sum.down.map((s) => s.kind)).toEqual(["storage"]);
    expect(sum.off.map((s) => s.kind)).toEqual(["smtp"]);
  });
});

describe("diskTone", () => {
  const GB = 1024 ** 3;
  const disk = (free: number, total: number): AdminStorage => ({
    blob_count: 0,
    blob_bytes: 0,
    projects: 0,
    deleted_projects: 0,
    free_bytes: free,
    volume_total_bytes: total,
    owners: [],
    computed_at: null,
  });

  it("мало места: danger везде, с 80% занятого: warning", () => {
    expect(diskTone(disk(4 * GB, 200 * GB))).toBe("danger");
    expect(diskTone(disk(30 * GB, 200 * GB))).toBe("warning");
    expect(diskTone(disk(86 * GB, 200 * GB))).toBe("neutral");
  });
});
