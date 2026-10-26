import { vi } from "vitest";
import { ApiError } from "@shared/api";
import {
  NO_REMOTE_STATUS,
  gitSyncApi,
  toStatusView,
  type ConflictFile,
  type ConflictFileDetail,
  type ConflictSession,
  type FileResolution,
  type GitOperation,
  type GitStatus,
} from "@entities/git-sync";
import type { TextDetail } from "../model/conflictModel";

// Поддельный сервер конфликтов для тестов экрана: те же ответы, что даёт
// контракт, плюс простая память (черновики, операция). Подменяет методы
// gitSyncApi, поэтому проходят настоящие хуки и настоящий экран.

export const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

const side = (
  author: string | null,
  at: string | null,
  size: number | null = 100,
  exists = true,
) => ({ exists, size, author, at });

const base = (
  overrides: Partial<ConflictFile> & Pick<ConflictFile, "path" | "kind">,
): ConflictFile => ({
  owner: null,
  action: "conflict",
  conflict_type: null,
  hunks: 0,
  open_hunks: 0,
  fields: 0,
  open_fields: 0,
  resolved: false,
  resolution: null,
  allowed: [],
  default_resolution: null,
  sides: {
    ours: side("Иван Смирнов", "2026-10-26T10:00:00Z"),
    theirs: side("Анна Петрова", "2026-10-26T11:00:00Z"),
    base: side("Иван Смирнов", "2026-10-20T10:00:00Z"),
  },
  copy_path: null,
  doc_id: null,
  ...overrides,
});

export const HUNK_KEYS = ["h-intro", "h-tasks", "h-end"] as const;

export const MAIN_TEX: TextDetail = {
  kind: "text",
  eol: "lf",
  truncated: false,
  segments: [
    {
      type: "clean",
      lines: [
        "\\documentclass{article}",
        "\\begin{document}",
        "Введение",
        "Первая строка.",
        "Вторая строка.",
        "Третья строка.",
        "Четвёртая строка.",
        "Пятая строка.",
      ],
    },
    {
      type: "hunk",
      key: HUNK_KEYS[0],
      ours: ["Цель: клиент-серверное приложение."],
      base: ["Цель: приложение."],
      theirs: ["Цель: веб-приложение."],
      ours_start: 9,
      result_start: 9,
    },
    { type: "clean", lines: ["Задачи:"] },
    {
      type: "hunk",
      key: HUNK_KEYS[1],
      ours: ["Задача А.", "Задача Б."],
      base: ["Задача А."],
      theirs: ["Задача А.", "Задача В."],
      ours_start: 11,
      result_start: 11,
    },
    { type: "clean", lines: ["Заключение"] },
    {
      type: "hunk",
      key: HUNK_KEYS[2],
      ours: ["Итог мой."],
      base: [],
      theirs: ["Итог их."],
      ours_start: 14,
      result_start: 14,
    },
    { type: "clean", lines: ["\\end{document}"] },
  ],
};

const FORM_DETAIL: ConflictFileDetail = {
  kind: "json",
  fields: [
    {
      pointer: "/title",
      label: "Тема",
      type: "scalar",
      base: "A",
      ours: "B",
      theirs: "C",
      allowed: ["mine", "theirs"],
      status: "conflict",
    },
  ],
};

const IMAGE_DETAIL: ConflictFileDetail = {
  kind: "binary",
  ours: side("Иван Смирнов", "2026-10-26T10:00:00Z", 1000),
  theirs: side("Анна Петрова", "2026-10-26T11:00:00Z", 2000),
  newer: "theirs",
  copy_path: "images/a.conflict-1.png",
};

const DELETE_DETAIL: ConflictFileDetail = {
  kind: "delete",
  deleted_by: "theirs",
};

export const buildFiles = (): ConflictFile[] => [
  base({
    path: "main.tex",
    kind: "text",
    conflict_type: "content",
    hunks: 3,
    open_hunks: 3,
    allowed: ["mine", "theirs"],
  }),
  base({
    path: ".hse-studio/forms/title.json",
    kind: "json",
    conflict_type: "fields",
    fields: 1,
    open_fields: 1,
    allowed: ["mine", "theirs"],
  }),
  base({
    path: "images/a.png",
    kind: "binary",
    conflict_type: "binary",
    allowed: ["mine", "theirs", "newest"],
    default_resolution: "newest",
    copy_path: "images/a.conflict-1.png",
  }),
  base({
    path: "appendix.tex",
    kind: "text",
    conflict_type: "deleted_by_them",
    allowed: ["mine", "theirs"],
    sides: {
      ours: side("Иван Смирнов", "2026-10-26T10:00:00Z"),
      theirs: side(null, null, null, false),
      base: side("Иван Смирнов", "2026-10-20T10:00:00Z"),
    },
  }),
  base({
    path: "references.bib",
    kind: "text",
    action: "merged",
    resolved: true,
  }),
  base({
    path: "chapters/one.tex",
    kind: "text",
    action: "take_theirs",
    resolved: true,
  }),
];

const countable = (file: ConflictFile): boolean => file.action === "conflict";

export type FakeConflicts = {
  session: ConflictSession;
  drafts: Record<string, FileResolution>;
  /** Подробности файлов, как их отдаёт сервер. */
  details: Record<string, ConflictFileDetail>;
  operation: GitOperation | null;
  saveCalls: Record<string, FileResolution>[];
  resolveCalls: {
    fingerprint: string;
    resolutions: Record<string, FileResolution> | null | undefined;
  }[];
  aborted: boolean;
  /** Следующий POST resolve вернёт эту ошибку. */
  failResolveWith: ApiError | null;
  failSave: boolean;
  /** Меняет план: дальше resolve со старым отпечатком даст plan_outdated. */
  rebuildPlan: (fingerprint: string, files?: ConflictFile[]) => void;
  startOperation: (id?: string) => void;
  finishOperation: (
    status: "succeeded" | "failed" | "cancelled",
    outcome?: string,
    phase?: string,
  ) => void;
  restore: () => void;
};

export const installFakeConflicts = (
  options: { files?: ConflictFile[] } = {},
): FakeConflicts => {
  const files = options.files ?? buildFiles();
  const fake: FakeConflicts = {
    session: {
      id: "session-1",
      fingerprint: "fp-1",
      ours: {
        commit: "a".repeat(40),
        author: "Иван Смирнов",
        at: "2026-10-26T10:00:00Z",
        message: "Дописан раздел",
      },
      theirs: {
        commit: "b".repeat(40),
        author: "Анна Петрова",
        at: "2026-10-26T11:00:00Z",
        message: "Переписано введение",
      },
      base: null,
      counts: {
        conflict: files.filter(countable).length,
        auto: files.filter((f) => !countable(f)).length,
        total: files.length,
      },
      unresolved: files.filter(countable).length,
      drafts_saved_at: null,
      warnings: [],
      files,
    },
    drafts: {},
    details: {
      "main.tex": MAIN_TEX,
      ".hse-studio/forms/title.json": FORM_DETAIL,
      "images/a.png": IMAGE_DETAIL,
      "appendix.tex": DELETE_DETAIL,
    },
    operation: null,
    saveCalls: [],
    resolveCalls: [],
    aborted: false,
    failResolveWith: null,
    failSave: false,
    rebuildPlan: (fingerprint, nextFiles) => {
      fake.session = {
        ...fake.session,
        fingerprint,
        ...(nextFiles ? { files: nextFiles } : {}),
      };
    },
    startOperation: (id = "op-resolve") => {
      fake.operation = {
        id,
        kind: "resolve",
        project_id: PROJECT_ID,
        status: "running",
        phase: "merge",
        percent: null,
        message: null,
        cancellable: true,
        started_at: "2026-10-26T12:00:00Z",
        finished_at: null,
        result: null,
        error: null,
      };
    },
    finishOperation: (status, outcome = "merged", phase = "push") => {
      if (!fake.operation) return;
      fake.operation = {
        ...fake.operation,
        status,
        phase,
        cancellable: false,
        finished_at: "2026-10-26T12:00:05Z",
        result:
          status === "succeeded"
            ? {
                outcome,
                pulled_commits: 1,
                pushed_commits: 2,
                merge_commit: "c".repeat(40),
                files_changed: 4,
                auto: [],
                conflicts: null,
                warnings: [],
              }
            : null,
        error:
          status === "failed"
            ? { code: "remote_moved", detail: "Репозиторий ушёл вперёд." }
            : null,
      };
    },
    restore: () => {
      vi.restoreAllMocks();
    },
  };

  // Пересчёт счётчиков по черновикам, как это делает сервер.
  const applyDrafts = (): void => {
    for (const file of fake.session.files) {
      if (!countable(file)) continue;
      const draft = fake.drafts[file.path];
      file.resolution = draft ?? null;
      if (!draft) continue;
      if (draft.kind === "hunks") {
        file.open_hunks = Math.max(
          file.hunks - Object.keys(draft.hunks).length,
          0,
        );
        file.resolved = file.hunks > 0 && file.open_hunks === 0;
      } else {
        file.open_hunks = 0;
        file.resolved = true;
      }
    }
    fake.session.unresolved = fake.session.files.filter(
      (f) => countable(f) && !f.resolved,
    ).length;
  };

  const statusOf = (): GitStatus => ({
    ...NO_REMOTE_STATUS,
    connected: true,
    ui_state: fake.operation?.status === "running" ? "syncing" : "conflicts",
    pending: {
      session_id: fake.session.id,
      files_total: fake.session.counts.conflict,
      files_open: fake.session.unresolved,
    },
    operation:
      fake.operation?.status === "running"
        ? {
            id: fake.operation.id,
            kind: "resolve",
            phase: "merge",
            percent: null,
            cancellable: true,
            started_at: fake.operation.started_at,
          }
        : null,
  });

  vi.spyOn(gitSyncApi, "getStatus").mockImplementation(() =>
    Promise.resolve(toStatusView(statusOf())),
  );
  vi.spyOn(gitSyncApi, "getConflicts").mockImplementation(() => {
    if (fake.aborted) {
      return Promise.reject(
        new ApiError("Нет конфликтов", "no_conflicts", 404),
      );
    }
    return Promise.resolve(structuredClone(fake.session));
  });
  vi.spyOn(gitSyncApi, "getConflictFile").mockImplementation((_id, path) => {
    const detail = fake.details[path];
    return detail
      ? Promise.resolve(structuredClone(detail))
      : Promise.reject(new ApiError("Нет файла", "no_conflicts", 404));
  });
  vi.spyOn(gitSyncApi, "getConflictDiff").mockImplementation(
    (_id, path, view) =>
      Promise.resolve({
        path,
        binary: false,
        patch: [
          `--- a/${path}`,
          `+++ b/${path}`,
          "@@ -1,1 +1,1 @@",
          `-старая строка (${view})`,
          `+новая строка (${view})`,
        ].join("\n"),
        truncated: false,
      }),
  );
  vi.spyOn(gitSyncApi, "getConflictBlob").mockImplementation(() =>
    Promise.resolve(new Blob(["x"], { type: "image/png" })),
  );
  vi.spyOn(gitSyncApi, "saveConflictDraft").mockImplementation(
    (_id, resolutions) => {
      if (fake.failSave) return Promise.reject(new Error("offline"));
      fake.saveCalls.push(structuredClone(resolutions));
      fake.drafts = { ...fake.drafts, ...resolutions };
      applyDrafts();
      return Promise.resolve();
    },
  );
  vi.spyOn(gitSyncApi, "resolveConflicts").mockImplementation((_id, params) => {
    fake.resolveCalls.push({
      fingerprint: params.fingerprint,
      resolutions: params.resolutions,
    });
    if (fake.failResolveWith) {
      const error = fake.failResolveWith;
      fake.failResolveWith = null;
      return Promise.reject(error);
    }
    if (params.fingerprint !== fake.session.fingerprint) {
      return Promise.reject(new ApiError("План устарел", "plan_outdated", 409));
    }
    fake.startOperation();
    return Promise.resolve({ operation_id: "op-resolve" });
  });
  vi.spyOn(gitSyncApi, "getOperation").mockImplementation(() =>
    fake.operation
      ? Promise.resolve(structuredClone(fake.operation))
      : Promise.reject(new ApiError("Нет операции", "not_found", 404)),
  );
  vi.spyOn(gitSyncApi, "cancelOperation").mockImplementation(() => {
    fake.finishOperation("cancelled");
    const operation = fake.operation;
    return operation
      ? Promise.resolve(structuredClone(operation))
      : Promise.reject(new ApiError("Нет операции", "not_found", 404));
  });
  vi.spyOn(gitSyncApi, "abortConflicts").mockImplementation(() => {
    fake.aborted = true;
    return Promise.resolve({ ...NO_REMOTE_STATUS });
  });

  return fake;
};
