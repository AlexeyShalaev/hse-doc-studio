// Построчное сравнение двух текстов, которые обе стороны держат в памяти.
//
// Готовый разбор диффа в проекте есть (`vcsDiff.model`), но он парсит unified
// patch, который присылает git. Здесь патча нет вовсе: есть буфер редактора и
// содержимое с диска, и сравнить их нужно на месте — при конфликте с внешней
// правкой. Поэтому свой LCS: он короткий и не тянет зависимость.

export type DiffLineKind = "context" | "add" | "del";

export type DiffLine = {
  kind: DiffLineKind;
  text: string;
  /** Номер строки слева (в исходном тексте); null у добавленных. */
  leftNo: number | null;
  /** Номер строки справа (в новом тексте); null у удалённых. */
  rightNo: number | null;
};

// Потолок на размер задачи: LCS квадратичен по памяти, а .tex-файл диплома —
// это тысячи строк. Выше порога честно отдаём «переписано целиком» вместо того,
// чтобы подвесить вкладку на матрице в сотни мегабайт.
const MAX_LINES = 3000;

/**
 * Таблица длин наибольшей общей подпоследовательности, плоским массивом.
 *
 * Плоский `Int32Array` вместо массива массивов — меньше выделений и лучше
 * локальность на файле в тысячи строк. Наружу торчит только `at`, поэтому
 * арифметика индекса не расползается по алгоритму.
 */
type Lcs = { at: (i: number, j: number) => number };

const lcsTable = (left: readonly string[], right: readonly string[]): Lcs => {
  const width = right.length + 1;
  const table = new Int32Array((left.length + 1) * width);
  // Индексы вычисляются из длин и всегда в границах; `?? 0` — дань строгой
  // проверке индексов, а не реальная ветка.
  const at = (i: number, j: number): number => table[i * width + j] ?? 0;
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      table[i * width + j] =
        left[i] === right[j]
          ? at(i + 1, j + 1) + 1
          : Math.max(at(i + 1, j), at(i, j + 1));
    }
  }
  return { at };
};

const wholeFileRewrite = (
  left: readonly string[],
  right: readonly string[],
): DiffLine[] => [
  ...left.map((text, i) => ({
    kind: "del" as const,
    text,
    leftNo: i + 1,
    rightNo: null,
  })),
  ...right.map((text, i) => ({
    kind: "add" as const,
    text,
    leftNo: null,
    rightNo: i + 1,
  })),
];

/** Построчный дифф: `left` — что было, `right` — что стало. */
export const diffLines = (leftText: string, rightText: string): DiffLine[] => {
  const left = leftText.split("\n");
  const right = rightText.split("\n");
  if (left.length > MAX_LINES || right.length > MAX_LINES) {
    return wholeFileRewrite(left, right);
  }

  const lcs = lcsTable(left, right);
  const out: DiffLine[] = [];
  // Индексы всегда в границах циклов; `?? ""` здесь — дань строгой проверке
  // индексов, а не реальная ветка.
  const leftAt = (index: number) => left[index] ?? "";
  const rightAt = (index: number) => right[index] ?? "";

  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (leftAt(i) === rightAt(j)) {
      out.push({
        kind: "context",
        text: leftAt(i),
        leftNo: i + 1,
        rightNo: j + 1,
      });
      i += 1;
      j += 1;
    } else if (lcs.at(i + 1, j) >= lcs.at(i, j + 1)) {
      out.push({ kind: "del", text: leftAt(i), leftNo: i + 1, rightNo: null });
      i += 1;
    } else {
      out.push({ kind: "add", text: rightAt(j), leftNo: null, rightNo: j + 1 });
      j += 1;
    }
  }
  while (i < left.length) {
    out.push({ kind: "del", text: leftAt(i), leftNo: i + 1, rightNo: null });
    i += 1;
  }
  while (j < right.length) {
    out.push({ kind: "add", text: rightAt(j), leftNo: null, rightNo: j + 1 });
    j += 1;
  }
  return out;
};

/** Только изменённые участки с несколькими строками контекста вокруг. */
export const diffHunks = (
  lines: readonly DiffLine[],
  context = 3,
): DiffLine[][] => {
  const changed = lines
    .map((line, index) => (line.kind === "context" ? -1 : index))
    .filter((index) => index >= 0);
  if (changed.length === 0) return [];

  const hunks: DiffLine[][] = [];
  const first = changed[0] ?? 0;
  let start = Math.max(0, first - context);
  let end = Math.min(lines.length - 1, first + context);
  for (const index of changed.slice(1)) {
    if (index - context <= end + 1) {
      end = Math.min(lines.length - 1, index + context);
      continue;
    }
    hunks.push(lines.slice(start, end + 1));
    start = Math.max(0, index - context);
    end = Math.min(lines.length - 1, index + context);
  }
  hunks.push(lines.slice(start, end + 1));
  return hunks;
};
