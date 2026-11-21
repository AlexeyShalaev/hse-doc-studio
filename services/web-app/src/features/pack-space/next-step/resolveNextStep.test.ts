import { describe, expect, it } from "vitest";
import { NO_CHANGES, type ChangesStatus } from "../changes/types";
import {
  isButtonStep,
  isPrimaryStep,
  resolveNextStep,
  type NextStep,
} from "./resolveNextStep";

const DRAFT = { pack: "p", template: "t", version: "2026.1.3" };
const open = (
  patch: Partial<Extract<ChangesStatus["request"], { kind: "open" }>> = {},
) =>
  ({
    kind: "open",
    number: 412,
    label: "#412",
    url: "https://example.test/pr/412",
    checks: "pending",
    progress: { done: 3, total: 5 },
    newEdits: false,
    ...patch,
  }) as const;

const status = (patch: Partial<ChangesStatus>): ChangesStatus => ({
  ...NO_CHANGES,
  ...patch,
});

type Row = [
  name: string,
  patch: Partial<ChangesStatus>,
  expected: NextStep | null,
];

// Двенадцать строк таблицы 4.3, затем граничные случаи.
const ROWS: Row[] = [
  ["1. клонируется", { connection: "cloning" }, { kind: "connecting" }],
  [
    "2. подключение не удалось",
    { connection: "failed" },
    { kind: "checkAccess" },
  ],
  [
    "3. выпущена, своих изменений нет",
    { released: true },
    { kind: "makeCopy" },
  ],
  [
    "4. выпущена, свои изменения в другой версии",
    { released: true, changedFiles: 4, changedElsewhere: DRAFT },
    { kind: "toDraft", version: DRAFT },
  ],
  [
    "5. черновик с ошибками",
    { changedFiles: 3, changedInVersion: 3, errors: 2 },
    { kind: "fixErrors", count: 2 },
  ],
  [
    "6. черновик без заметок",
    { changedFiles: 3, changedInVersion: 3, notesNeeded: true },
    { kind: "describe" },
  ],
  [
    "7. черновик, всё готово",
    { changedFiles: 3, changedInVersion: 3 },
    { kind: "submit" },
  ],
  [
    "8. запрос открыт, новых правок нет",
    { changedFiles: 3, changedInVersion: 3, request: open() },
    {
      kind: "request",
      label: "#412",
      checks: "pending",
      progress: { done: 3, total: 5 },
    },
  ],
  [
    "9. запрос открыт, есть новые правки",
    { changedFiles: 4, changedInVersion: 4, request: open({ newEdits: true }) },
    { kind: "updateRequest" },
  ],
  [
    "10. запрос принят",
    {
      changedFiles: 3,
      request: { kind: "merged", number: 412, label: "#412" },
    },
    { kind: "startNew" },
  ],
  ["11. папка на диске", { workspaceKind: "folder" }, { kind: "folder" }],
  ["12. черновик, правок ещё нет", {}, null],
];

describe("resolveNextStep: строки таблицы 4.3", () => {
  it.each(ROWS)("%s", (_name, patch, expected) => {
    expect(resolveNextStep(status(patch))).toEqual(expected);
  });
});

describe("resolveNextStep: приоритет и граничные случаи", () => {
  it("ошибки важнее заметок, заметки важнее отправки", () => {
    const base = { changedFiles: 3, changedInVersion: 3 };
    expect(
      resolveNextStep(status({ ...base, errors: 1, notesNeeded: true })),
    ).toEqual({ kind: "fixErrors", count: 1 });
    expect(resolveNextStep(status({ ...base, notesNeeded: true }))).toEqual({
      kind: "describe",
    });
  });

  it("пока git читается или не прочитался, кнопки нет", () => {
    expect(
      resolveNextStep(status({ load: "loading", released: true })),
    ).toBeNull();
    expect(
      resolveNextStep(status({ load: "failed", changedFiles: 3 })),
    ).toBeNull();
  });

  it("подключение разбирается раньше всего, даже при незагруженном git", () => {
    expect(
      resolveNextStep(status({ connection: "cloning", load: "loading" })),
    ).toEqual({ kind: "connecting" });
    expect(
      resolveNextStep(status({ connection: "failed", released: true })),
    ).toEqual({ kind: "checkAccess" });
  });

  it("папка: главной кнопки нет, даже у выпущенной версии", () => {
    const step = resolveNextStep(
      status({ workspaceKind: "folder", released: true }),
    );
    expect(step).toEqual({ kind: "folder" });
    expect(step && isButtonStep(step)).toBe(false);
  });

  it("принятый запрос важнее «Править копию», ошибок и заметок", () => {
    const merged = { kind: "merged", number: 7, label: "!7" } as const;
    expect(
      resolveNextStep(status({ released: true, request: merged })),
    ).toEqual({ kind: "startNew" });
    expect(
      resolveNextStep(
        status({
          errors: 2,
          notesNeeded: true,
          changedFiles: 1,
          request: merged,
        }),
      ),
    ).toEqual({ kind: "startNew" });
  });

  it("выпущена и отправлена: свои изменения в самой версии, запрос открыт", () => {
    expect(
      resolveNextStep(
        status({
          released: true,
          changedFiles: 3,
          changedInVersion: 3,
          request: open(),
        }),
      ),
    ).toMatchObject({ kind: "request" });
    // Выпуск сделан, отправка оборвалась: запроса ещё нет, кнопка зовёт отправить.
    expect(
      resolveNextStep(
        status({ released: true, changedFiles: 3, changedInVersion: 3 }),
      ),
    ).toEqual({ kind: "submit" });
  });

  it("выпущена, изменения только вне версий: отправка, а не копия", () => {
    expect(
      resolveNextStep(status({ released: true, changedFiles: 1 })),
    ).toEqual({ kind: "submit" });
  });

  it("выпущена, запрос открыт, но своих правок нет: он, а не «Править копию»", () => {
    expect(
      resolveNextStep(status({ released: true, request: open() })),
    ).toMatchObject({ kind: "request" });
  });

  it("запрос закрыт без слияния: правки отправляются заново, пустое пространство молчит", () => {
    const closed = { kind: "closed", number: 5, label: "#5" } as const;
    expect(
      resolveNextStep(
        status({ changedFiles: 2, changedInVersion: 2, request: closed }),
      ),
    ).toEqual({ kind: "submit" });
    expect(resolveNextStep(status({ request: closed }))).toBeNull();
  });

  it("ошибки при открытом запросе: сначала исправить, потом обновлять", () => {
    expect(
      resolveNextStep(
        status({
          changedFiles: 4,
          errors: 1,
          request: open({ newEdits: true }),
        }),
      ),
    ).toEqual({ kind: "fixErrors", count: 1 });
  });

  it("вторичный шаг один: «Запрос #N · …», остальные кнопки главные", () => {
    expect(
      isPrimaryStep({
        kind: "request",
        label: "#1",
        checks: "unknown",
        progress: null,
      }),
    ).toBe(false);
    for (const [, patch] of ROWS) {
      const step = resolveNextStep(status(patch));
      if (step && step.kind !== "request" && isButtonStep(step)) {
        expect(isPrimaryStep(step)).toBe(true);
      }
    }
  });
});
