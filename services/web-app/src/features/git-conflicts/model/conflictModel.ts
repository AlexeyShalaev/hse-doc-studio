import type {
  ConflictFile,
  ConflictFileDetail,
  ConflictSession,
  FieldChoice,
  FileResolution,
  HunkChoice,
  JsonFieldConflict,
} from "@entities/git-sync";

// Чистая модель экрана конфликтов: что выбрано, что ещё открыто, как из выборов
// собрать итоговый текст. Никакого React и сети: всё считается на месте, поэтому
// счётчики в шапке меняются сразу по щелчку, а не после ответа сервера.

export type TextDetail = Extract<ConflictFileDetail, { kind: "text" }>;
export type TextSegment = TextDetail["segments"][number];
export type HunkSegment = Extract<TextSegment, { type: "hunk" }>;
export type JsonDetail = Extract<ConflictFileDetail, { kind: "json" }>;
export type BinaryDetail = Extract<ConflictFileDetail, { kind: "binary" }>;

/** Выборы по файлам: путь -> решение. Совпадает с телом PUT /conflicts/draft. */
export type DraftMap = Record<string, FileResolution>;

/** Как решено одно место конфликта. */
export type HunkChoiceValue =
  "mine" | "theirs" | "both" | "both_reverse" | "base" | "custom";

/** Быстрые выборы на карточке (остальные: «исходное» и свой текст). */
export const QUICK_HUNK_CHOICES = [
  "mine",
  "theirs",
  "both",
  "both_reverse",
] as const satisfies readonly HunkChoiceValue[];

export const isTextDetail = (
  detail: ConflictFileDetail | undefined,
): detail is TextDetail => detail?.kind === "text";

export const hunksOf = (detail: TextDetail): HunkSegment[] =>
  detail.segments.filter((s): s is HunkSegment => s.type === "hunk");

export const isJsonDetail = (
  detail: ConflictFileDetail | undefined,
): detail is JsonDetail => detail?.kind === "json";

export const isBinaryDetail = (
  detail: ConflictFileDetail | undefined,
): detail is BinaryDetail => detail?.kind === "binary";

/** Нужно ли решение пользователя (остальные файлы сервер решил сам). */
export const needsDecision = (file: ConflictFile): boolean =>
  file.action === "conflict";

/** Один удалил файл, другой изменил. */
export const isDeleteConflict = (file: ConflictFile): boolean =>
  file.conflict_type === "deleted_by_us" ||
  file.conflict_type === "deleted_by_them";

/** Конфликты, которые решаются целым набором: подписи и имена по регистру. */
export const isGroupConflict = (file: ConflictFile): boolean =>
  file.conflict_type === "signature_group" ||
  file.conflict_type === "case_collision";

// --- выбор по местам --------------------------------------------------------------

/** Что выбрано по местам; для решения другого вида места не выбраны. */
export const chosenHunks = (
  resolution: FileResolution | null | undefined,
): Record<string, HunkChoice> =>
  resolution?.kind === "hunks" ? resolution.hunks : {};

export const setHunkChoice = (
  resolution: FileResolution | null | undefined,
  key: string,
  choice: HunkChoice,
): FileResolution => ({
  kind: "hunks",
  hunks: { ...chosenHunks(resolution), [key]: choice },
});

/**
 * Снимает выбор. Пустое решение по местам остаётся (а не превращается в null):
 * сервер хранит черновики по пути, и «ничего не выбрано» надо передать явно.
 */
export const clearHunkChoice = (
  resolution: FileResolution | null | undefined,
  key: string,
): FileResolution => {
  const { [key]: _removed, ...rest } = chosenHunks(resolution);
  return { kind: "hunks", hunks: rest };
};

/** Одно решение на все места файла («всё моё», «всё их»). */
export const chooseAllHunks = (
  detail: TextDetail,
  choice: "mine" | "theirs",
): FileResolution => ({
  kind: "hunks",
  hunks: Object.fromEntries(
    hunksOf(detail).map((h) => [h.key, { choice }] as const),
  ),
});

// --- выбор по полям ---------------------------------------------------------------

/** Как решено одно поле. */
export type FieldChoiceValue = "mine" | "theirs" | "union";

/** Поля, где стороны разошлись и нужен выбор. */
export const conflictFieldsOf = (detail: JsonDetail): JsonFieldConflict[] =>
  detail.fields.filter((f) => f.status === "conflict");

/** Поля, которые сервер слил сам: решать в них нечего. */
export const autoFieldsOf = (detail: JsonDetail): JsonFieldConflict[] =>
  detail.fields.filter((f) => f.status !== "conflict");

export const isFieldChoice = (value: string): value is FieldChoiceValue =>
  value === "mine" || value === "theirs" || value === "union";

/** Сохранённый выбор по полям; решение другого вида полей не выбирает. */
export const chosenFields = (
  resolution: FileResolution | null | undefined,
): Record<string, FieldChoice> =>
  resolution?.kind === "fields" ? resolution.fields : {};

/**
 * Что выбрано по каждому полю. Выбор «файл целиком: моё или их» (черновик
 * старого вида или быстрый выбор) значит то же самое для каждого поля, если оно
 * такой вариант допускает.
 */
export const fieldChoicesFor = (
  detail: JsonDetail,
  resolution: FileResolution | null | undefined,
): Record<string, FieldChoiceValue> => {
  const result: Record<string, FieldChoiceValue> = {};
  const fields = conflictFieldsOf(detail);
  if (resolution?.kind === "file" && isFieldChoice(resolution.choice)) {
    const whole = resolution.choice;
    for (const field of fields) {
      if (field.allowed.includes(whole)) result[field.pointer] = whole;
    }
    return result;
  }
  const chosen = chosenFields(resolution);
  for (const field of fields) {
    const choice = chosen[field.pointer]?.choice;
    if (choice && isFieldChoice(choice) && field.allowed.includes(choice)) {
      result[field.pointer] = choice;
    }
  }
  return result;
};

export const setFieldChoice = (
  detail: JsonDetail,
  resolution: FileResolution | null | undefined,
  pointer: string,
  choice: FieldChoiceValue,
): FileResolution => ({
  kind: "fields",
  fields: Object.fromEntries(
    Object.entries({
      ...fieldChoicesFor(detail, resolution),
      [pointer]: choice,
    }).map(([key, value]) => [key, { choice: value }] as const),
  ),
});

/** Снимает выбор по полю; пустое решение остаётся, как и для мест. */
export const clearFieldChoice = (
  detail: JsonDetail,
  resolution: FileResolution | null | undefined,
  pointer: string,
): FileResolution => {
  const { [pointer]: _removed, ...rest } = fieldChoicesFor(detail, resolution);
  return {
    kind: "fields",
    fields: Object.fromEntries(
      Object.entries(rest).map(
        ([key, value]) => [key, { choice: value }] as const,
      ),
    ),
  };
};

/** «Всё моё» и «Всё их»: каждому полю, которое такой выбор допускает. */
export const chooseAllFields = (
  detail: JsonDetail,
  choice: "mine" | "theirs",
): FileResolution => ({
  kind: "fields",
  fields: Object.fromEntries(
    conflictFieldsOf(detail)
      .filter((f) => f.allowed.length === 0 || f.allowed.includes(choice))
      .map((f) => [f.pointer, { choice }] as const),
  ),
});

export type FieldsProgress = { open: number; total: number; resolved: number };

/** Сколько полей решено и сколько осталось: по подробностям файла. */
export const fieldsProgress = (
  detail: JsonDetail,
  resolution: FileResolution | null | undefined,
): FieldsProgress => {
  const total = conflictFieldsOf(detail).length;
  const resolved = Object.keys(fieldChoicesFor(detail, resolution)).length;
  return { total, resolved, open: total - resolved };
};

export const openFieldPointers = (
  detail: JsonDetail,
  resolution: FileResolution | null | undefined,
): string[] => {
  const chosen = fieldChoicesFor(detail, resolution);
  return conflictFieldsOf(detail)
    .map((f) => f.pointer)
    .filter((pointer) => !(pointer in chosen));
};

/** Значения полей равны по содержимому (порядок ключей объекта не важен). */
export const sameValue = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) {
    return (
      Array.isArray(a) &&
      Array.isArray(b) &&
      a.length === b.length &&
      a.every((item, i) => sameValue(item, b[i]))
    );
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    const left = a as Record<string, unknown>;
    const right = b as Record<string, unknown>;
    const keys = Object.keys(left);
    return (
      keys.length === Object.keys(right).length &&
      keys.every((key) => key in right && sameValue(left[key], right[key]))
    );
  }
  return false;
};

/** Объединение двух списков: сначала мои значения, затем только чужие. */
export const unionValue = (field: JsonFieldConflict): unknown[] | null => {
  if (!Array.isArray(field.ours) || !Array.isArray(field.theirs)) return null;
  const merged: unknown[] = [...(field.ours as unknown[])];
  for (const item of field.theirs as unknown[]) {
    if (!merged.some((existing) => sameValue(existing, item))) {
      merged.push(item);
    }
  }
  return merged;
};

/** Чьё значение сервер взял в поле, которое слил сам. */
export const autoFieldWinner = (
  field: JsonFieldConflict,
): "same" | "mine" | "theirs" => {
  if (sameValue(field.ours, field.theirs)) return "same";
  if (sameValue(field.ours, field.base)) return "theirs";
  return "mine";
};

export const setFileChoice = (choice: string): FileResolution => ({
  kind: "file",
  choice,
});

export const setManualText = (content: string): FileResolution => ({
  kind: "text",
  content,
});

// --- прогресс ---------------------------------------------------------------------

export type FileProgress = {
  resolved: boolean;
  /** Сколько мест (полей) осталось решить; у файла целиком это 0 или 1. */
  open: number;
  total: number;
};

const countChosen = (keys: string[], chosen: Record<string, unknown>): number =>
  keys.filter((k) => k in chosen).length;

/**
 * Состояние файла с учётом локального выбора. Без выбора верим серверу: он мог
 * сохранить черновик раньше или решить файл по умолчанию.
 */
export const fileProgress = (
  file: ConflictFile,
  resolution: FileResolution | null | undefined,
  /** Ключи мест файла, если подробности уже загружены: точнее, чем счётчик. */
  knownHunkKeys?: string[],
  /** То же для полей: указатели полей, где нужен выбор. */
  knownFieldPointers?: string[],
): FileProgress => {
  if (!needsDecision(file)) return { resolved: true, open: 0, total: 0 };
  const total = file.hunks + file.fields;
  if (!resolution) {
    return {
      resolved: file.resolved,
      open: file.resolved ? 0 : Math.max(file.open_hunks + file.open_fields, 1),
      total: Math.max(total, 1),
    };
  }
  switch (resolution.kind) {
    case "file": {
      const allowed =
        file.allowed.length === 0 || file.allowed.includes(resolution.choice);
      return { resolved: allowed, open: allowed ? 0 : 1, total: 1 };
    }
    case "text":
      return { resolved: true, open: 0, total: Math.max(total, 1) };
    case "hunks": {
      const keys = Object.keys(resolution.hunks);
      const done = knownHunkKeys
        ? countChosen(knownHunkKeys, resolution.hunks)
        : keys.length;
      const open = Math.max(file.hunks - done, 0);
      // Файл без мест (например, удаление против правки) решением по местам не решить.
      return {
        resolved: file.hunks > 0 && open === 0,
        open: file.hunks > 0 ? open : 1,
        total: Math.max(file.hunks, 1),
      };
    }
    case "fields": {
      const done = knownFieldPointers
        ? countChosen(knownFieldPointers, resolution.fields)
        : Object.keys(resolution.fields).length;
      const open = Math.max(file.fields - done, 0);
      return {
        resolved: file.fields > 0 && open === 0,
        open: file.fields > 0 ? open : 1,
        total: Math.max(file.fields, 1),
      };
    }
  }
};

export type SessionProgress = {
  /** Файлов, где нужно решение. */
  total: number;
  resolved: number;
  open: number;
  /** Сколько мест и полей осталось решить во всех файлах. */
  openItems: number;
  openPaths: string[];
};

export const sessionProgress = (
  session: ConflictSession,
  drafts: DraftMap,
): SessionProgress => {
  const files = session.files.filter(needsDecision);
  const openPaths: string[] = [];
  let openItems = 0;
  for (const file of files) {
    const progress = fileProgress(file, drafts[file.path]);
    if (!progress.resolved) {
      openPaths.push(file.path);
      openItems += progress.open;
    }
  }
  return {
    total: files.length,
    resolved: files.length - openPaths.length,
    open: openPaths.length,
    openItems,
    openPaths,
  };
};

// Обход по кругу: начиная со следующего за `from` (или с края, если его нет).
const ringOrder = (
  length: number,
  from: number,
  direction: 1 | -1,
): number[] => {
  const begin = from < 0 ? (direction === 1 ? -1 : length) : from;
  return Array.from(
    { length },
    (_, step) =>
      (((begin + direction * (step + 1)) % length) + length) % length,
  );
};

/** Следующий файл с нерешённым местом после `from` (по кругу), либо null. */
export const nextOpenPath = (
  session: ConflictSession,
  drafts: DraftMap,
  from: string | null,
  direction: 1 | -1 = 1,
): string | null => {
  const files = session.files.filter(needsDecision);
  const order = ringOrder(
    files.length,
    files.findIndex((f) => f.path === from),
    direction,
  );
  for (const index of order) {
    const file = files[index];
    if (file && !fileProgress(file, drafts[file.path]).resolved) {
      return file.path;
    }
  }
  return null;
};

/** Ключи нерешённых мест файла в порядке следования. */
export const openHunkKeys = (
  detail: TextDetail,
  resolution: FileResolution | null | undefined,
): string[] => {
  const chosen = chosenHunks(resolution);
  return hunksOf(detail)
    .map((h) => h.key)
    .filter((key) => !(key in chosen));
};

/** Следующее нерешённое место после `from` (по кругу), либо null. */
export const nextOpenHunkKey = (
  detail: TextDetail,
  resolution: FileResolution | null | undefined,
  from: string | null,
  direction: 1 | -1 = 1,
): string | null => {
  const all = hunksOf(detail).map((h) => h.key);
  const open = new Set(openHunkKeys(detail, resolution));
  const order = ringOrder(all.length, all.indexOf(from ?? ""), direction);
  for (const index of order) {
    const key = all[index];
    if (key !== undefined && open.has(key)) return key;
  }
  return null;
};

// --- итоговый текст ---------------------------------------------------------------

const splitLines = (text: string): string[] => text.split(/\r?\n/);

/** Строки, которые выбор по месту кладёт в итог. Нет выбора: моя версия. */
export const hunkResultLines = (
  hunk: HunkSegment,
  choice: HunkChoice | undefined,
): string[] => {
  switch (choice?.choice) {
    case "theirs":
      return hunk.theirs;
    case "both":
      return [...hunk.ours, ...hunk.theirs];
    case "both_reverse":
      return [...hunk.theirs, ...hunk.ours];
    case "base":
      return hunk.base;
    case "custom":
      return splitLines(choice.text ?? "");
    default:
      return hunk.ours;
  }
};

/** Итог по месту одним текстом (для поля ручной правки). */
export const composeHunkText = (
  hunk: HunkSegment,
  choice: HunkChoice | undefined,
): string => hunkResultLines(hunk, choice).join("\n");

/** Файл целиком, как он получится при текущих выборах (нерешённое: моё). */
export const composeText = (
  detail: TextDetail,
  resolution: FileResolution | null | undefined,
): string => {
  if (resolution?.kind === "text") return resolution.content;
  const chosen = chosenHunks(resolution);
  const lines: string[] = [];
  for (const segment of detail.segments) {
    if (segment.type === "clean") lines.push(...segment.lines);
    else lines.push(...hunkResultLines(segment, chosen[segment.key]));
  }
  return lines.join(detail.eol === "crlf" ? "\r\n" : "\n");
};

// Служебные строки, которые git оставляет на месте конфликта.
const MARKER_LINE = /^(<{7}|>{7}|\|{7})( |$)/;

/** В тексте остались строки-метки конфликта: такой файл отправлять нельзя. */
export const hasConflictMarkers = (text: string): boolean =>
  splitLines(text).some((line) => MARKER_LINE.test(line));

// --- согласование с новым сеансом ---------------------------------------------------

/**
 * Что оставить из выборов, когда сеанс пересобран (чужие изменения обновились
 * или файл правили, пока шёл разбор): выборы по файлам, которые всё ещё
 * конфликтуют. Места сверяются по ключам, как только известны подробности.
 */
export const carryOverDrafts = (
  drafts: DraftMap,
  session: ConflictSession,
): DraftMap => {
  const open = new Map(
    session.files.filter(needsDecision).map((f) => [f.path, f] as const),
  );
  const next: DraftMap = {};
  for (const [path, resolution] of Object.entries(drafts)) {
    const file = open.get(path);
    if (!file) continue;
    if (resolution.kind === "file" && file.allowed.length > 0) {
      if (!file.allowed.includes(resolution.choice)) continue;
    }
    next[path] = resolution;
  }
  return next;
};

/** Выкидывает выборы по местам и полям, которых в файле больше нет. */
export const pruneResolution = (
  resolution: FileResolution,
  detail: ConflictFileDetail,
): FileResolution => {
  if (resolution.kind === "hunks" && detail.kind === "text") {
    const keys = new Set(hunksOf(detail).map((h) => h.key));
    const kept = Object.fromEntries(
      Object.entries(resolution.hunks).filter(([key]) => keys.has(key)),
    );
    return Object.keys(kept).length === Object.keys(resolution.hunks).length
      ? resolution
      : { kind: "hunks", hunks: kept };
  }
  if (resolution.kind === "fields" && detail.kind === "json") {
    // Поле осталось, но варианта, который выбрал пользователь, в нём уже нет:
    // такой выбор тоже сбрасываем, иначе сервер отклонит весь файл.
    const fields = new Map(
      conflictFieldsOf(detail).map((f) => [f.pointer, f] as const),
    );
    const kept = Object.fromEntries(
      Object.entries(resolution.fields).filter(([pointer, value]) => {
        const field = fields.get(pointer);
        return !!field && field.allowed.includes(value.choice);
      }),
    );
    return Object.keys(kept).length === Object.keys(resolution.fields).length
      ? resolution
      : { kind: "fields", fields: kept };
  }
  return resolution;
};

/** Решения, которые сохранил сервер (после перезагрузки страницы). */
export const draftsFromSession = (session: ConflictSession): DraftMap => {
  const drafts: DraftMap = {};
  for (const file of session.files) {
    if (needsDecision(file) && file.resolution) {
      drafts[file.path] = file.resolution;
    }
  }
  return drafts;
};

/** Сеанс как «версия»: меняется, когда пересобран план слияния. */
export const sessionKey = (session: ConflictSession): string =>
  `${session.id}:${session.fingerprint}`;

export const isSameResolution = (
  a: FileResolution | null | undefined,
  b: FileResolution | null | undefined,
): boolean => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
