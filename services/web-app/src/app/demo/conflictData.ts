import type {
  ConflictDiff,
  ConflictFile,
  ConflictFileDetail,
  ConflictSession,
  FileResolution,
} from "@entities/git-sync";
import { DAY, HOUR, fakeSha, isoAgo } from "./clock";
import { ME, TEAMMATES } from "./people";

// Один конфликтный сеанс на все виды конфликтов: текст с тремя местами, поля
// формы, картинка, удаление против правки и автоматически решённые файлы.

export type DemoConflictSession = {
  session: ConflictSession;
  details: Record<string, ConflictFileDetail>;
  drafts: Record<string, FileResolution>;
};

const ANNA = TEAMMATES[0]?.name ?? "Анна Петрова";

const TEX_HUNKS = {
  intro: {
    key: "main.tex:a41c",
    ours: [
      "Целью работы является разработка клиент-серверного приложения для",
      "синхронизации учебных документов между участниками команды.",
    ],
    base: [
      "Целью работы является разработка приложения для работы с документами.",
    ],
    theirs: [
      "Целью работы является разработка веб-приложения для совместной работы",
      "над документами по ГОСТ.",
    ],
  },
  tasks: {
    key: "main.tex:7be0",
    ours: [
      "  \\item проанализировать существующие системы контроля версий;",
      "  \\item спроектировать протокол обмена изменениями;",
      "  \\item реализовать слияние правок на уровне абзацев.",
    ],
    base: [
      "  \\item проанализировать существующие системы;",
      "  \\item реализовать прототип.",
    ],
    theirs: [
      "  \\item проанализировать существующие системы;",
      "  \\item спроектировать интерфейс разрешения конфликтов;",
      "  \\item реализовать прототип;",
      "  \\item провести пользовательское тестирование.",
    ],
  },
  conclusion: {
    key: "main.tex:c9d2",
    ours: [
      "Разработанный подход позволяет объединять правки без потери данных,",
      "однако требует аккуратной работы с бинарными файлами.",
    ],
    base: [
      "Разработанный подход позволяет объединять правки без потери данных.",
    ],
    theirs: [
      "Разработанный подход позволяет объединять правки без потери данных",
      "и подходит для работы команды из нескольких человек.",
    ],
  },
} as const;

const mainTexDetail: ConflictFileDetail = {
  kind: "text",
  eol: "lf",
  truncated: false,
  segments: [
    {
      type: "clean",
      lines: [
        "\\documentclass[14pt]{extarticle}",
        "\\usepackage[russian]{babel}",
        "\\usepackage{hse-coursework}",
        "",
        "\\begin{document}",
        "\\section*{Введение}",
        "Актуальность темы определяется ростом числа проектов, над которыми",
        "работает несколько авторов.",
      ],
    },
    {
      type: "hunk",
      key: TEX_HUNKS.intro.key,
      ours: [...TEX_HUNKS.intro.ours],
      base: [...TEX_HUNKS.intro.base],
      theirs: [...TEX_HUNKS.intro.theirs],
      ours_start: 9,
      result_start: 9,
    },
    {
      type: "clean",
      lines: [
        "",
        "Для достижения цели необходимо решить следующие задачи:",
        "\\begin{itemize}",
      ],
    },
    {
      type: "hunk",
      key: TEX_HUNKS.tasks.key,
      ours: [...TEX_HUNKS.tasks.ours],
      base: [...TEX_HUNKS.tasks.base],
      theirs: [...TEX_HUNKS.tasks.theirs],
      ours_start: 14,
      result_start: 13,
    },
    {
      type: "clean",
      lines: [
        "\\end{itemize}",
        "",
        "\\section*{Заключение}",
        "В работе рассмотрены методы слияния текстовых документов.",
      ],
    },
    {
      type: "hunk",
      key: TEX_HUNKS.conclusion.key,
      ours: [...TEX_HUNKS.conclusion.ours],
      base: [...TEX_HUNKS.conclusion.base],
      theirs: [...TEX_HUNKS.conclusion.theirs],
      ours_start: 22,
      result_start: 22,
    },
    { type: "clean", lines: ["", "\\end{document}"] },
  ],
};

const formDetail: ConflictFileDetail = {
  kind: "json",
  fields: [
    {
      pointer: "/answers/title",
      label: "Тема работы",
      type: "scalar",
      base: "Разработка приложения для работы с документами",
      ours: "Разработка клиент-серверного приложения для синхронизации документов",
      theirs: "Разработка веб-приложения для совместной работы над документами",
      allowed: ["mine", "theirs"],
      status: "conflict",
    },
    {
      pointer: "/answers/supervisor",
      label: "Научный руководитель",
      type: "scalar",
      base: "Иванов И. И.",
      ours: "Иванов И. И.",
      theirs: "Петров П. П.",
      allowed: ["mine", "theirs"],
      status: "conflict",
    },
    {
      pointer: "/answers/keywords",
      label: "Ключевые слова",
      type: "list",
      base: ["git"],
      ours: ["git", "синхронизация"],
      theirs: ["git", "LaTeX"],
      allowed: ["mine", "theirs", "union"],
      status: "conflict",
    },
    {
      pointer: "/answers/year",
      label: "Год защиты",
      type: "scalar",
      base: 2025,
      ours: 2025,
      theirs: 2026,
      allowed: ["mine", "theirs"],
      status: "auto",
    },
  ],
};

const imageDetail: ConflictFileDetail = {
  kind: "binary",
  ours: { exists: true, size: 184_320, author: ME.name, at: isoAgo(2 * HOUR) },
  theirs: { exists: true, size: 203_776, author: ANNA, at: isoAgo(5 * HOUR) },
  newer: "ours",
  copy_path: "images/architecture.conflict-4f2a9c1.png",
};

const appendixDetail: ConflictFileDetail = {
  kind: "delete",
  deleted_by: "theirs",
};

const side = (
  exists: boolean,
  size: number | null,
  author: string | null,
  agoMs: number | null,
) => ({
  exists,
  size,
  author,
  at: agoMs === null ? null : isoAgo(agoMs),
});

const file = (
  partial: Partial<ConflictFile> & Pick<ConflictFile, "path" | "kind">,
): ConflictFile => ({
  owner: ME.name,
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
    ours: side(true, 4_120, ME.name, 2 * HOUR),
    theirs: side(true, 4_380, ANNA, 5 * HOUR),
    base: side(true, 3_900, ME.name, 3 * DAY),
  },
  copy_path: null,
  doc_id: null,
  ...partial,
});

const FILES: ConflictFile[] = [
  file({
    path: "main.tex",
    kind: "text",
    conflict_type: "content",
    hunks: 3,
    open_hunks: 3,
    allowed: ["mine", "theirs"],
    owner: ME.name,
    doc_id: "coursework",
  }),
  file({
    path: ".hse-studio/forms/title-page.json",
    kind: "json",
    conflict_type: "fields",
    fields: 3,
    open_fields: 3,
    allowed: ["mine", "theirs"],
    owner: ANNA,
    sides: {
      ours: side(true, 812, ME.name, 90 * 60_000),
      theirs: side(true, 846, ANNA, 4 * HOUR),
      base: side(true, 790, ME.name, 3 * DAY),
    },
  }),
  file({
    path: "images/architecture.png",
    kind: "binary",
    conflict_type: "binary",
    allowed: ["mine", "theirs", "newest"],
    default_resolution: "newest",
    owner: ANNA,
    copy_path: "images/architecture.conflict-4f2a9c1.png",
    sides: {
      ours: side(true, 184_320, ME.name, 2 * HOUR),
      theirs: side(true, 203_776, ANNA, 5 * HOUR),
      base: side(true, 150_000, ME.name, 5 * DAY),
    },
  }),
  file({
    path: "chapters/appendix.tex",
    kind: "text",
    conflict_type: "deleted_by_them",
    allowed: ["mine", "theirs"],
    owner: ME.name,
    sides: {
      ours: side(true, 2_048, ME.name, 6 * HOUR),
      theirs: side(false, null, null, null),
      base: side(true, 1_950, ME.name, 4 * DAY),
    },
  }),
  file({
    path: "references.bib",
    kind: "text",
    action: "merged",
    resolved: true,
    owner: ANNA,
    sides: {
      ours: side(true, 5_210, ME.name, 8 * HOUR),
      theirs: side(true, 5_644, ANNA, 7 * HOUR),
      base: side(true, 4_900, ME.name, 6 * DAY),
    },
  }),
  file({
    path: "chapters/introduction.tex",
    kind: "text",
    action: "take_theirs",
    resolved: true,
    owner: ANNA,
    doc_id: "coursework",
  }),
  file({
    path: "images/results.png",
    kind: "binary",
    action: "binary_newest",
    resolved: true,
    copy_path: "images/results.conflict-b71d0e4.png",
    owner: ANNA,
  }),
  file({
    path: "chapters/old-draft.tex",
    kind: "text",
    action: "delete",
    resolved: true,
    sides: {
      ours: side(false, null, null, null),
      theirs: side(false, null, null, null),
      base: side(true, 1_200, ME.name, 9 * DAY),
    },
  }),
];

const countable = (f: ConflictFile): boolean => f.action === "conflict";

export const buildConflictSession = (): DemoConflictSession => {
  const files = FILES.map((f) => structuredClone(f));
  const conflicts = files.filter(countable).length;
  return {
    session: {
      id: fakeSha("conflict-session").slice(0, 12),
      fingerprint: fakeSha("conflict-fingerprint"),
      ours: {
        commit: fakeSha("ours-tip"),
        author: ME.name,
        at: isoAgo(10 * 60_000),
        message: "Дописан раздел про слияние",
      },
      theirs: {
        commit: fakeSha("theirs-tip"),
        author: ANNA,
        at: isoAgo(20 * 60_000),
        message: "Переписала введение",
      },
      base: {
        commit: fakeSha("base-tip"),
        author: ME.name,
        at: isoAgo(3 * DAY),
        message: "Первая версия",
      },
      counts: {
        conflict: conflicts,
        auto: files.length - conflicts,
        total: files.length,
      },
      unresolved: conflicts,
      drafts_saved_at: null,
      warnings: [{ code: "signatures_stale", paths: ["signatures.json"] }],
      files,
    },
    details: {
      "main.tex": mainTexDetail,
      ".hse-studio/forms/title-page.json": formDetail,
      "images/architecture.png": imageDetail,
      "chapters/appendix.tex": appendixDetail,
    },
    drafts: {},
  };
};

// Пересчёт счётчиков по сохранённым черновикам. Сервер делает то же самое.
export const applyDrafts = (state: DemoConflictSession): void => {
  for (const f of state.session.files) {
    if (!countable(f)) continue;
    const draft = state.drafts[f.path];
    f.resolution = draft ?? null;
    if (!draft) {
      f.open_hunks = f.hunks;
      f.open_fields = f.fields;
      f.resolved = false;
      continue;
    }
    if (draft.kind === "hunks") {
      f.open_hunks = Math.max(f.hunks - Object.keys(draft.hunks).length, 0);
      f.resolved = f.open_hunks === 0;
    } else if (draft.kind === "fields") {
      f.open_fields = Math.max(f.fields - Object.keys(draft.fields).length, 0);
      f.resolved = f.open_fields === 0;
    } else {
      f.open_hunks = 0;
      f.open_fields = 0;
      f.resolved = true;
    }
  }
  const open = state.session.files.filter((f) => countable(f) && !f.resolved);
  state.session.unresolved = open.length;
  state.session.drafts_saved_at = isoAgo(0);
};

export const openConflictPaths = (state: DemoConflictSession): string[] =>
  state.session.files
    .filter((f) => countable(f) && !f.resolved)
    .map((f) => f.path);

// --- diff -------------------------------------------------------------------------

const patchFor = (path: string, view: "ours" | "theirs" | "result"): string => {
  if (path === "main.tex") {
    if (view === "ours") {
      return [
        "--- a/main.tex",
        "+++ b/main.tex",
        "@@ -9,1 +9,2 @@",
        "-Целью работы является разработка приложения для работы с документами.",
        "+Целью работы является разработка клиент-серверного приложения для",
        "+синхронизации учебных документов между участниками команды.",
        "@@ -14,2 +14,3 @@",
        "-  \\item проанализировать существующие системы;",
        "-  \\item реализовать прототип.",
        "+  \\item проанализировать существующие системы контроля версий;",
        "+  \\item спроектировать протокол обмена изменениями;",
        "+  \\item реализовать слияние правок на уровне абзацев.",
      ].join("\n");
    }
    if (view === "theirs") {
      return [
        "--- a/main.tex",
        "+++ b/main.tex",
        "@@ -9,1 +9,2 @@",
        "-Целью работы является разработка приложения для работы с документами.",
        "+Целью работы является разработка веб-приложения для совместной работы",
        "+над документами по ГОСТ.",
        "@@ -14,2 +14,4 @@",
        "   \\item проанализировать существующие системы;",
        "-  \\item реализовать прототип.",
        "+  \\item спроектировать интерфейс разрешения конфликтов;",
        "+  \\item реализовать прототип;",
        "+  \\item провести пользовательское тестирование.",
      ].join("\n");
    }
    return [
      "--- a/main.tex",
      "+++ b/main.tex",
      "@@ -9,2 +9,2 @@",
      " Целью работы является разработка клиент-серверного приложения для",
      "-синхронизации учебных документов между участниками команды.",
      "+совместной работы над документами по ГОСТ.",
    ].join("\n");
  }
  if (path.endsWith(".json")) {
    return [
      `--- a/${path}`,
      `+++ b/${path}`,
      "@@ -3,3 +3,3 @@",
      '-    "title": "Разработка приложения для работы с документами",',
      view === "theirs"
        ? '+    "title": "Разработка веб-приложения для совместной работы над документами",'
        : '+    "title": "Разработка клиент-серверного приложения для синхронизации документов",',
      '     "supervisor": "Иванов И. И."',
    ].join("\n");
  }
  if (path === "chapters/appendix.tex") {
    return [
      "--- a/chapters/appendix.tex",
      "+++ /dev/null",
      "@@ -1,3 +0,0 @@",
      "-\\section*{Приложение А}",
      "-Описание формата файла настроек.",
      "-\\input{tables/config}",
    ].join("\n");
  }
  return "";
};

export const conflictDiff = (
  path: string,
  view: "ours" | "theirs" | "result",
): ConflictDiff => {
  const patch = patchFor(path, view);
  return {
    path,
    binary: patch === "",
    patch,
    truncated: false,
  };
};

// Содержимое файла для просмотра. Картинки — маленький SVG под нужным именем:
// браузер показывает его так же, как настоящий файл.
export const conflictBlobText = (path: string, side: string): string => {
  if (path.endsWith(".png")) {
    const color =
      side === "theirs" ? "#2f6fdc" : side === "base" ? "#8a8f98" : "#1f9d62";
    return `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="300" viewBox="0 0 480 300"><rect width="480" height="300" fill="${color}" opacity="0.15"/><rect x="40" y="50" width="130" height="60" rx="8" fill="${color}"/><rect x="310" y="50" width="130" height="60" rx="8" fill="${color}"/><rect x="175" y="190" width="130" height="60" rx="8" fill="${color}"/><path d="M170 80h140M105 110l70 80M375 110l-70 80" stroke="${color}" stroke-width="4" fill="none"/></svg>`;
  }
  return `Содержимое ${path} (${side})`;
};
