import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import en from "../../../shared/lib/i18n/locales/en/admin/diagnostics.json";
import ru from "../../../shared/lib/i18n/locales/ru/admin/diagnostics.json";
import { JOB_STATES } from "../../admin-ops/lib/jobs";
import {
  CHECK_TARGETS,
  TARGETS,
  targetKeyOf,
  targetOf,
  type DiagTargetKey,
} from "./targets";

const SRC = resolve(__dirname, "../../..");
const read = (rel: string): string => readFileSync(resolve(SRC, rel), "utf8");

// Проверки, которые знает сервер: CheckId в core/diagnostics/entities.py.
const backendCheckIds = (): string[] => {
  const source = readFileSync(
    resolve(SRC, "../../api/hse_doc_studio/core/diagnostics/entities.py"),
    "utf8",
  );
  const body =
    /class CheckId\(StrEnum\):([\s\S]*?)\n\n/.exec(source)?.[1] ?? "";
  return [...body.matchAll(/^\s+(\w+)\s*=/gm)].map((m) => m[1] ?? "");
};

// Разделы админки, которые есть в меню (AdminLayout) и во вкладках RunnersPage.
const adminPaths = (): string[] =>
  [
    ...read("pages/AdminPage/AdminLayout.tsx").matchAll(
      /to: "(\/admin[^"]*)"/g,
    ),
  ].map((m) => m[1] ?? "");
const RUNNER_TABS = ["runners", "queue"];

describe("цели строк самодиагностики", () => {
  it("список проверок сервера не пуст и совпадает со словарём", () => {
    const ids = backendCheckIds();
    expect(ids.length).toBeGreaterThan(5);
    expect(Object.keys(ru.check).sort()).toEqual([...ids].sort());
  });

  it("у каждой проверки сервера цель назначена явно: раздел или null", () => {
    for (const id of backendCheckIds()) {
      expect(Object.keys(CHECK_TARGETS), `проверка ${id}`).toContain(id);
    }
    // Лишних записей нет: проверку убрали, запись осталась.
    expect(Object.keys(CHECK_TARGETS).sort()).toEqual(
      [...backendCheckIds()].sort(),
    );
  });

  it("каждый адрес ведёт на существующий раздел, вкладку, фильтр и якорь", () => {
    const paths = adminPaths();
    expect(paths.length).toBeGreaterThan(10);
    for (const [key, to] of Object.entries(TARGETS)) {
      const url = new URL(to, "http://x");
      expect(paths, `${key}: раздел ${url.pathname}`).toContain(url.pathname);
      const tab = url.searchParams.get("tab");
      if (tab) {
        expect(url.pathname).toBe("/admin/runners");
        expect(RUNNER_TABS, `${key}: вкладка`).toContain(tab);
      }
      const state = url.searchParams.get("state");
      if (state) {
        expect(tab).toBe("queue");
        expect(JOB_STATES as readonly string[], `${key}: состояние`).toContain(
          state,
        );
      }
      if (url.hash) {
        const id = url.hash.slice(1);
        const found = [
          "features/admin-backups/ui/BackupsPage.tsx",
          "features/admin-auth-settings/ui/SmtpSection.tsx",
          "features/admin-install/ui/InstanceForm.tsx",
        ].some((file) => read(file).includes(`id="${id}"`));
        expect(found, `${key}: якорь #${id} есть в разделе`).toBe(true);
      }
    }
  });

  it("подписи цели есть в ru и en для каждого ключа", () => {
    for (const key of Object.keys(TARGETS)) {
      expect(ru.target, key).toHaveProperty(key);
      expect(en.target, key).toHaveProperty(key);
    }
    expect(Object.keys(ru.target).sort()).toEqual(
      [...Object.keys(TARGETS), "label"].sort(),
    );
    expect(Object.keys(en.target).sort()).toEqual(
      Object.keys(ru.target).sort(),
    );
  });

  it("все цели из таблицы действительно используются", () => {
    const used = new Set<DiagTargetKey>(
      Object.values(CHECK_TARGETS).filter(
        (k): k is DiagTargetKey => k !== null,
      ),
    );
    for (const id of backendCheckIds()) {
      for (const reason of Object.keys(ru.reason)) {
        const key = targetKeyOf({ id, reason });
        if (key) used.add(key);
      }
    }
    expect([...used].sort()).toEqual(Object.keys(TARGETS).sort());
  });

  it("точная причина уточняет цель, без причины остаётся цель проверки", () => {
    expect(targetOf({ id: "jobs", reason: "jobs_stuck" })?.to).toBe(
      "/admin/runners?tab=queue&state=running",
    );
    expect(targetOf({ id: "jobs", reason: "ok" })?.to).toBe(
      "/admin/runners?tab=queue",
    );
    expect(targetOf({ id: "runners", reason: "no_runners" })?.to).toBe(
      "/admin/runners?create=token",
    );
    expect(targetOf({ id: "backups", reason: null })?.to).toBe(
      "/admin/backups",
    );
    expect(targetOf({ id: "database", reason: "db_unreachable" })).toBeNull();
    expect(targetOf({ id: "unknown_new", reason: null })).toBeNull();
  });
});
