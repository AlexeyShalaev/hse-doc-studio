import type {
  MatrixCell,
  MatrixCellStatus,
  MatrixRow,
  OutcomeSection,
} from "@entities/pack-studio";
import type { RunTally } from "./scenarios";

// Матрица «сценарии на разделы» (template-studio-outcome.md, раздел 3.6). Статус клетки, счётчик и
// пометку «против базы» считает сервер; здесь только итог по строкам и группы одинаковых отпечатков.

/** Итог по строкам матрицы в виде прогона, чтобы строка «N совпало, M изменилось» была та же, что у F8. */
export const tallyRows = (
  rows: readonly MatrixRow[],
  broken: number,
): RunTally => ({
  passed: rows.filter((row) => row.status === "passed").length,
  failed: rows.filter((row) => row.status === "failed").length,
  errors: rows.filter((row) => row.status === "error").length,
  unchecked: rows.filter((row) => row.status === "unchecked").length,
  broken,
  total: rows.length,
});

/** Клетка строки по разделу (в ответе клетки идут по `columns`, но порядок не предполагаем). */
export const cellOf = (
  row: MatrixRow,
  section: OutcomeSection,
): MatrixCell | undefined => row.cells.find((cell) => cell.section === section);

/** Сколько клеток в каждом статусе: счётчики под таблицей. */
export const countCells = (
  rows: readonly MatrixRow[],
): Record<MatrixCellStatus, number> => {
  const out: Record<MatrixCellStatus, number> = {
    matched: 0,
    changed: 0,
    unchecked: 0,
    error: 0,
  };
  for (const row of rows) for (const cell of row.cells) out[cell.status] += 1;
  return out;
};

/**
 * Группы одинаковых отпечатков в столбце: буква у клеток, чей раздел у нескольких сценариев
 * одинаковый («эти сценарии ничего не различают»). Единичные отпечатки и клетки без результата
 * без буквы. Буквы идут по порядку появления в столбце.
 */
export const fingerprintGroups = (
  rows: readonly MatrixRow[],
  section: OutcomeSection,
): ReadonlyMap<string, string> => {
  const seen = new Map<string, number>();
  for (const row of rows) {
    const cell = cellOf(row, section);
    if (cell && cell.status !== "error" && cell.fingerprint !== "") {
      seen.set(cell.fingerprint, (seen.get(cell.fingerprint) ?? 0) + 1);
    }
  }
  const letters = new Map<string, string>();
  for (const [fingerprint, count] of seen) {
    if (count < 2) continue;
    const at = letters.size;
    letters.set(
      fingerprint,
      at < 26 ? String.fromCharCode(65 + at) : String(at + 1),
    );
  }
  return letters;
};
