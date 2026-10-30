import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import en from "@shared/lib/i18n/locales/en/admin/users.json";
import ru from "@shared/lib/i18n/locales/ru/admin/users.json";
import { createDemoAdminPeople } from "./adminPeople";
import { DEMO_AUDIT_ACTIONS } from "./scaleWorld";

// Действия журнала берутся из кода бэкенда: у каждого кода, который пишет
// сервер, есть подпись на обоих языках, иначе в журнале всплывает сырой код.
// Демо пишет только те же коды.

const API = join(
  import.meta.dirname,
  ...Array<string>(5).fill(".."),
  "api",
  "hse_doc_studio",
);

const DOMAINS =
  "auth|admin|account|audit|group|invite|oidc|org|pat|project|queue|runner|settings|setup|signing|git|submission";
// Литерал действия в файле, который пишет в журнал: «домен.действие».
const ACTION = new RegExp(`"((?:${DOMAINS})\\.[a-z_]+(?:\\.[a-z_]+)?)"`, "g");

const pyFiles = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory())
      return entry.name === "migrations" ? [] : pyFiles(path);
    return entry.name.endsWith(".py") ? [path] : [];
  });

const apiActions = (): Set<string> => {
  const out = new Set<string>();
  for (const file of pyFiles(API)) {
    const text = readFileSync(file, "utf8");
    // Только места записи в журнал: иначе в выборку попадут права доступа.
    if (!/_audit\.record\(|audit\.record\(/.test(text)) continue;
    for (const match of text.matchAll(ACTION)) {
      const [, action] = match;
      if (action) out.add(action);
    }
  }
  return out;
};

const key = (action: string) => action.replaceAll(".", "_");

describe("подписи действий журнала", () => {
  const actions = apiActions();

  it("находит действия в коде бэкенда", () => {
    expect(actions.size).toBeGreaterThan(30);
    expect(actions).toContain("auth.login");
  });

  it("у каждого действия сервера есть подпись на русском и английском", () => {
    const ruActions: Record<string, string> = ru.audit.actions;
    const enActions: Record<string, string> = en.audit.actions;
    const missing = [...actions].filter(
      (action) => !ruActions[key(action)] || !enActions[key(action)],
    );
    expect(missing).toEqual([]);
  });

  it("демо пишет только действия, которые есть у сервера", () => {
    const demo = [
      ...DEMO_AUDIT_ACTIONS,
      ...createDemoAdminPeople("default").audit.map((e) => e.action),
    ];
    const fake = [...new Set(demo)].filter((action) => !actions.has(action));
    expect(fake).toEqual([]);
  });
});
