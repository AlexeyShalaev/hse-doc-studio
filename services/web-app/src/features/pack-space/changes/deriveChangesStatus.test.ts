import { describe, expect, it } from "vitest";
import type {
  PackCiStatus,
  PackDiagnostic,
  PackFileChange,
  PackGit,
  PackLint,
  PackVersionRef,
} from "@entities/pack-studio";
import { GALLERY_REF, GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";
import {
  MAX_LINT_TARGETS,
  deriveChangesStatus,
  isNotesFinding,
  isNumberFinding,
  lintTargets,
  readNotes,
  type ChangesRaw,
} from "./deriveChangesStatus";
import { NO_CHANGES } from "./types";

const DRAFT = "hse-cs-sse/templates/coursework/versions/2026.1.3";
const RELEASED = "hse-cs-sse/templates/coursework/versions/2026.1.2";
const RELEASED_REF: PackVersionRef = { ...GALLERY_REF, version: "2026.1.2" };

const file = (
  path: string,
  status: PackFileChange["status"] = "modified",
): PackFileChange => ({ path, status });

const gitOf = (patch: Partial<PackGit> = {}): PackGit => ({
  workspace: {
    ...GALLERY_WORKSPACE,
    work_branch: "pack-studio/ivanov/coursework",
  },
  provider: "github",
  head_sha: "aaa",
  branch: "pack-studio/ivanov/coursework",
  base_branch: "master",
  uncommitted: [],
  dirty: false,
  changed: [],
  ahead: 0,
  behind: 0,
  compare_url: null,
  ...patch,
});

const diagnostic = (patch: Partial<PackDiagnostic> = {}): PackDiagnostic => ({
  severity: "error",
  check: "lint",
  message: "ошибка",
  path: `${DRAFT}/version.yaml`,
  line: 3,
  pointer: null,
  ...patch,
});

const lintOf = (
  findings: PackDiagnostic[],
  patch: Partial<PackLint> = {},
): PackLint => ({
  scope: "version",
  target: DRAFT,
  released: false,
  errors: findings.filter((f) => f.severity === "error").length,
  warnings: findings.filter((f) => f.severity === "warning").length,
  findings,
  ...patch,
});

const NOTES = { ru: ["Раз"], en: ["One"] };

const rawOf = (patch: Partial<ChangesRaw> = {}): ChangesRaw => ({
  workspace: GALLERY_WORKSPACE,
  tree: GALLERY_TREE,
  open: GALLERY_REF,
  git: gitOf(),
  gitLoad: "ready",
  ci: null,
  lint: [],
  notes: NOTES,
  ...patch,
});

const ci = (patch: Partial<PackCiStatus> = {}): PackCiStatus => ({
  state: "pending",
  sha: "aaa",
  checks: [],
  available: true,
  reason: null,
  web_url: null,
  pr_state: "open",
  ...patch,
});

const withRequest = (git: Partial<PackGit> = {}): PackGit =>
  gitOf({
    ...git,
    workspace: {
      ...GALLERY_WORKSPACE,
      work_branch: "pack-studio/ivanov/coursework",
      pr_number: 412,
      pr_url: "https://github.com/o/r/pull/412",
      pushed_sha: "aaa",
      ...git.workspace,
    },
  });

describe("deriveChangesStatus: данные и подключение", () => {
  it("git ещё читается: load, остальное по нулям", () => {
    expect(
      deriveChangesStatus(rawOf({ git: null, gitLoad: "loading" })),
    ).toEqual({ ...NO_CHANGES, load: "loading" });
  });

  it("git не прочитался: failed", () => {
    expect(
      deriveChangesStatus(rawOf({ git: null, gitLoad: "failed" })).load,
    ).toBe("failed");
  });

  it("пространство клонируется или не подключилось: git не спрашиваем", () => {
    for (const [state, connection] of [
      ["cloning", "cloning"],
      ["failed", "failed"],
    ] as const) {
      const status = deriveChangesStatus(
        rawOf({
          workspace: { ...GALLERY_WORKSPACE, state },
          git: null,
          gitLoad: "loading",
        }),
      );
      expect(status).toEqual({ ...NO_CHANGES, connection });
    }
  });

  it("папка на диске: вид folder, изменений и запроса нет", () => {
    const status = deriveChangesStatus(
      rawOf({
        workspace: { ...GALLERY_WORKSPACE, kind: "folder" },
        git: null,
        gitLoad: "ready",
      }),
    );
    expect(status).toEqual({ ...NO_CHANGES, workspaceKind: "folder" });
  });

  it("замок: открытая версия выпущена", () => {
    expect(deriveChangesStatus(rawOf()).released).toBe(false);
    expect(deriveChangesStatus(rawOf({ open: RELEASED_REF })).released).toBe(
      true,
    );
  });
});

describe("deriveChangesStatus: изменения", () => {
  it("ничего не менялось: нули", () => {
    expect(deriveChangesStatus(rawOf())).toEqual(NO_CHANGES);
  });

  it("число файлов: всё пространство, из них в открытой версии", () => {
    const status = deriveChangesStatus(
      rawOf({
        git: gitOf({
          changed: [
            file(`${DRAFT}/version.yaml`),
            file(`${DRAFT}/files/ts/doc.yaml`),
            file("hse-cs-sse/pack.yaml"),
          ],
        }),
      }),
    );
    expect(status.changedFiles).toBe(3);
    expect(status.changedInVersion).toBe(2);
    expect(status.changedElsewhere).toBeNull();
  });

  it("правки только в другой версии: она в changedElsewhere", () => {
    const status = deriveChangesStatus(
      rawOf({
        open: RELEASED_REF,
        git: gitOf({ changed: [file(`${DRAFT}/version.yaml`)] }),
      }),
    );
    expect(status).toMatchObject({
      released: true,
      changedFiles: 1,
      changedInVersion: 0,
      changedElsewhere: GALLERY_REF,
    });
  });

  it("другая версия: черновик важнее выпущенной, новее важнее старой", () => {
    const tree = structuredClone(GALLERY_TREE);
    const versions = tree.packs[0]?.templates[0]?.versions;
    versions?.push({
      version: "2026.1.10",
      path: DRAFT.replace("2026.1.3", "2026.1.10"),
      status: "beta",
      released: false,
      modified: false,
    });
    const status = deriveChangesStatus(
      rawOf({
        tree,
        open: RELEASED_REF,
        git: gitOf({
          changed: [
            file(`${RELEASED}/version.yaml`),
            file(`${DRAFT}/version.yaml`),
            file(`${DRAFT.replace("2026.1.3", "2026.1.10")}/version.yaml`),
          ],
        }),
      }),
    );
    // Числовое сравнение номеров: 2026.1.10 новее 2026.1.3.
    expect(status.changedElsewhere?.version).toBe("2026.1.10");
  });

  it("удалённые файлы считаются, но не проверяются", () => {
    const changed = [
      file(`${DRAFT}/files/ts/old.tex`, "deleted"),
      file(`${DRAFT}/version.yaml`),
    ];
    expect(
      deriveChangesStatus(rawOf({ git: gitOf({ changed }) })).changedFiles,
    ).toBe(2);
    expect(lintTargets(changed.slice(0, 1), GALLERY_REF)).toEqual([]);
  });

  it("отставание от основной ветки", () => {
    expect(
      deriveChangesStatus(rawOf({ git: gitOf({ behind: 4 }) })).behind,
    ).toBe(4);
  });
});

describe("deriveChangesStatus: проверки и заметки", () => {
  const changed = [file(`${DRAFT}/version.yaml`)];

  it("ошибки и замечания суммируются по местам", () => {
    const status = deriveChangesStatus(
      rawOf({
        git: gitOf({ changed }),
        lint: [
          lintOf([diagnostic(), diagnostic({ severity: "warning" })]),
          lintOf([diagnostic()], {
            target: "hse-cs-sse/pack.yaml",
            scope: "file",
          }),
        ],
      }),
    );
    expect(status).toMatchObject({
      errors: 2,
      warnings: 1,
      notesNeeded: false,
    });
  });

  it("находка про заметки не ошибка, а шаг «Описать изменения»", () => {
    const notes = diagnostic({
      message: "version.yaml: `changes.en` — непустой список заметок о версии",
    });
    const status = deriveChangesStatus(
      rawOf({
        git: gitOf({ changed }),
        notes: { ru: ["Раз"], en: [] },
        lint: [lintOf([notes, diagnostic()])],
      }),
    );
    expect(status).toMatchObject({ errors: 1, notesNeeded: true });
  });

  it("находка про заметки без правок в открытой версии шаг не вызывает", () => {
    const notes = diagnostic({ message: "`changes` разной длины по языкам" });
    const status = deriveChangesStatus(
      rawOf({
        git: gitOf({
          changed: [
            file(`${DRAFT.replace("2026.1.3", "2026.1.9")}/version.yaml`),
          ],
        }),
        lint: [
          lintOf([notes], {
            target: DRAFT.replace("2026.1.3", "2026.1.9"),
          }),
        ],
        notes: null,
      }),
    );
    expect(status).toMatchObject({ errors: 0, notesNeeded: false });
  });

  it("заметок нет у черновика с правками: нужны, это не ошибка", () => {
    const status = deriveChangesStatus(
      rawOf({ git: gitOf({ changed }), notes: { ru: [], en: [] } }),
    );
    expect(status).toMatchObject({ errors: 0, notesNeeded: true });
  });

  it("заметки на одном языке мало: нужны", () => {
    expect(
      deriveChangesStatus(
        rawOf({ git: gitOf({ changed }), notes: { ru: ["Раз"], en: [] } }),
      ).notesNeeded,
    ).toBe(true);
  });

  it("правок в версии нет или манифест ещё не прочитан: заметки не требуем", () => {
    expect(
      deriveChangesStatus(rawOf({ notes: { ru: [], en: [] } })).notesNeeded,
    ).toBe(false);
    expect(
      deriveChangesStatus(rawOf({ git: gitOf({ changed }), notes: null }))
        .notesNeeded,
    ).toBe(false);
  });

  it("выпущенной версии заметки не пишут", () => {
    expect(
      deriveChangesStatus(
        rawOf({
          open: RELEASED_REF,
          git: gitOf({ changed: [file(`${RELEASED}/version.yaml`)] }),
          notes: { ru: [], en: [] },
        }),
      ).notesNeeded,
    ).toBe(false);
  });

  it("у выпущенной версии находка про заметки остаётся ошибкой", () => {
    const status = deriveChangesStatus(
      rawOf({
        open: RELEASED_REF,
        git: gitOf({ changed: [file(`${RELEASED}/version.yaml`)] }),
        lint: [
          lintOf([diagnostic({ message: "`changes.en` пусто" })], {
            target: RELEASED,
            released: true,
          }),
        ],
      }),
    );
    expect(status).toMatchObject({ errors: 1, notesNeeded: false });
  });

  it("распознаёт находку про заметки", () => {
    expect(isNotesFinding(diagnostic({ message: "`changes.ru` пусто" }))).toBe(
      true,
    );
    expect(isNotesFinding(diagnostic({ message: "поле `changes_x`" }))).toBe(
      false,
    );
    expect(
      isNotesFinding(diagnostic({ severity: "warning", message: "`changes`" })),
    ).toBe(false);
  });
});

describe("deriveChangesStatus: запрос на слияние", () => {
  const changed = [file(`${DRAFT}/version.yaml`)];

  it("PR нет: kind none, даже если ветка отправлена", () => {
    expect(
      deriveChangesStatus(
        rawOf({
          git: gitOf({
            changed,
            workspace: { ...GALLERY_WORKSPACE, pushed_sha: "aaa" },
          }),
        }),
      ).request,
    ).toEqual({ kind: "none" });
  });

  it.each([
    ["pending", "pending"],
    ["success", "passed"],
    ["failure", "failed"],
    ["awaiting_approval", "awaiting_approval"],
    ["none", "unknown"],
    ["unknown", "unknown"],
  ] as const)("запрос открыт, проверки %s: %s", (state, checks) => {
    const status = deriveChangesStatus(
      rawOf({ git: withRequest({ changed }), ci: ci({ state }) }),
    );
    expect(status.request).toMatchObject({
      kind: "open",
      number: 412,
      label: "#412",
      checks,
      newEdits: false,
    });
  });

  it("проверки ещё не пришли: открыт, статус unknown", () => {
    expect(
      deriveChangesStatus(rawOf({ git: withRequest({ changed }) })).request,
    ).toMatchObject({ kind: "open", checks: "unknown", progress: null });
  });

  it("ход проверок: завершённые из всех", () => {
    const status = deriveChangesStatus(
      rawOf({
        git: withRequest({ changed }),
        ci: ci({
          checks: [
            { name: "a", state: "success", url: null, summary: null },
            { name: "b", state: "failure", url: null, summary: null },
            { name: "c", state: "running", url: null, summary: null },
            { name: "d", state: "queued", url: null, summary: null },
            { name: "e", state: "skipped", url: null, summary: null },
          ],
        }),
      }),
    );
    expect(status.request).toMatchObject({ progress: { done: 3, total: 5 } });
  });

  it("GitLab: метка с восклицательным знаком", () => {
    const status = deriveChangesStatus(
      rawOf({ git: withRequest({ changed, provider: "gitlab" }), ci: ci() }),
    );
    expect(status.request).toMatchObject({ label: "!412" });
  });

  it("новые правки: несохранённое или коммит после отправки", () => {
    const dirty = deriveChangesStatus(
      rawOf({ git: withRequest({ changed, dirty: true }), ci: ci() }),
    );
    expect(dirty.request).toMatchObject({ newEdits: true });
    const moved = deriveChangesStatus(
      rawOf({ git: withRequest({ changed, head_sha: "bbb" }), ci: ci() }),
    );
    expect(moved.request).toMatchObject({ newEdits: true });
  });

  it("запрос принят и закрыт", () => {
    expect(
      deriveChangesStatus(
        rawOf({
          git: withRequest({ changed }),
          ci: ci({ pr_state: "merged" }),
        }),
      ).request,
    ).toEqual({ kind: "merged", number: 412, label: "#412" });
    expect(
      deriveChangesStatus(
        rawOf({
          git: withRequest({ changed }),
          ci: ci({ pr_state: "closed" }),
        }),
      ).request,
    ).toEqual({ kind: "closed", number: 412, label: "#412" });
  });
});

describe("lintTargets", () => {
  it("открытая версия первой, затем остальные по алфавиту, не больше предела", () => {
    const changed = [
      file("hse-cs-sse/pack.yaml"),
      file(`${RELEASED}/version.yaml`),
      file(`${DRAFT}/files/ts/doc.yaml`),
      file(`${DRAFT}/version.yaml`),
      file("hse-cs-sse/templates/coursework/template.yaml"),
    ];
    const targets = lintTargets(changed, GALLERY_REF);
    expect(targets).toHaveLength(MAX_LINT_TARGETS);
    expect(targets[0]).toBe(DRAFT);
    expect(targets.slice(1)).toEqual([
      "hse-cs-sse/pack.yaml",
      "hse-cs-sse/templates/coursework/template.yaml",
    ]);
  });

  it("файл без линтера (картинка в общей папке пака) места не даёт", () => {
    expect(lintTargets([file("hse-cs-sse/README.md")], GALLERY_REF)).toEqual(
      [],
    );
  });
});

describe("readNotes", () => {
  it("читает ru и en, пустые пункты отбрасывает", () => {
    expect(readNotes({ changes: { ru: ["Раз", "  "], en: ["One"] } })).toEqual({
      ru: ["Раз"],
      en: ["One"],
    });
  });

  it("нет блока, не словарь, не массив: пусто", () => {
    expect(readNotes(undefined)).toEqual({ ru: [], en: [] });
    expect(readNotes({ changes: "text" })).toEqual({ ru: [], en: [] });
    expect(readNotes({ changes: { ru: "x" } })).toEqual({ ru: [], en: [] });
  });
});

describe("deriveChangesStatus: копия версии", () => {
  const NEW_FILES = [
    ...Array.from({ length: 13 }, (_, i) =>
      file(`${DRAFT}/files/d${String(i)}/doc.yaml`, "added"),
    ),
    ...Array.from({ length: 13 }, (_, i) =>
      file(`${DRAFT}/files/d${String(i)}/d${String(i)}.ru.tex`, "added"),
    ),
    file(`${DRAFT}/version.yaml`, "added"),
  ];
  const same = new Set(
    NEW_FILES.map((c) => c.path).filter(
      (path) => !path.includes("d0/") && !path.endsWith("d5.ru.tex"),
    ),
  );
  const copy = { dir: DRAFT, base: "2026.1.2", same, pending: false };

  it("без сверки считаем по git: вся копия это изменение", () => {
    const status = deriveChangesStatus(
      rawOf({ git: gitOf({ changed: NEW_FILES }) }),
    );
    expect(status.changedFiles).toBe(27);
  });

  it("со сверкой считаем только отличия от версии-основы", () => {
    const status = deriveChangesStatus(
      rawOf({ git: gitOf({ changed: NEW_FILES }), copy }),
    );
    expect(status.changedFiles).toBe(3);
    expect(status.changedInVersion).toBe(3);
  });

  it("копия без правок: изменений нет, кнопки нет", () => {
    const status = deriveChangesStatus(
      rawOf({
        git: gitOf({ changed: NEW_FILES }),
        copy: {
          ...copy,
          same: new Set(NEW_FILES.map((c) => c.path)),
        },
      }),
    );
    expect(status.changedFiles).toBe(0);
    expect(status.notesNeeded).toBe(false);
  });

  it("находка про номер версии не ошибка и не заметки", () => {
    const status = deriveChangesStatus(
      rawOf({
        git: gitOf({ changed: NEW_FILES }),
        copy,
        lint: [
          lintOf([
            diagnostic({
              message:
                "release: номер 2026.1.3 после 2026.1.2 это patch, а изменения требуют не меньше minor: Состав или языки документа: documents[ts].supported_kinds",
              path: null,
              line: null,
            }),
          ]),
        ],
      }),
    );
    expect(status.errors).toBe(0);
    expect(status.notesNeeded).toBe(false);
  });

  it("в выпущенной версии номер уже не поменять: это обычная ошибка", () => {
    const finding = diagnostic({
      message:
        "release: номер 2026.1.3 после 2026.1.2 это patch, а изменения требуют не меньше minor: x",
    });
    expect(isNumberFinding(finding)).toBe(true);
    expect(
      deriveChangesStatus(
        rawOf({
          git: gitOf({ changed: [file(`${DRAFT}/version.yaml`)] }),
          lint: [lintOf([finding], { released: true })],
        }),
      ).errors,
    ).toBe(1);
  });

  it("мягче класса в манифесте: номером не исправить, остаётся ошибкой", () => {
    expect(
      isNumberFinding(
        diagnostic({
          message:
            "release: `release.kind: patch` мягче класса версии 2026.2.0 (minor)",
        }),
      ),
    ).toBe(false);
  });
});
