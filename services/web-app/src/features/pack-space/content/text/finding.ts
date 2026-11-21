import type { PackDiagnostic } from "@entities/pack-studio";

// Плашка «ближайшее замечание» под редактором (pack-studio-ux.md, 5.5). Чистые функции: какое
// замечание показать и можно ли его исправить само.

/** Замечания этого файла: сначала ближайшее к строке курсора, при равенстве ошибка раньше предупреждения. */
export const pickFinding = (
  findings: readonly PackDiagnostic[] | undefined,
  path: string,
  caretLine: number,
): PackDiagnostic | null => {
  let best: PackDiagnostic | null = null;
  let bestKey: [number, number] | null = null;
  for (const finding of findings ?? []) {
    if (finding.path !== path) continue;
    const key: [number, number] = [
      finding.line === null
        ? Number.MAX_SAFE_INTEGER
        : Math.abs(finding.line - caretLine),
      finding.severity === "error" ? 0 : 1,
    ];
    if (
      bestKey === null ||
      key[0] < bestKey[0] ||
      (key[0] === bestKey[0] && key[1] < bestKey[1])
    ) {
      best = finding;
      bestKey = key;
    }
  }
  return best;
};

/** Расстояние Левенштейна (строки короткие: имена полей). */
const distance = (a: string, b: string): number => {
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const row = [i];
    for (let j = 1; j <= b.length; j += 1) {
      row.push(
        Math.min(
          (prev[j] ?? 0) + 1,
          (row[j - 1] ?? 0) + 1,
          (prev[j - 1] ?? 0) + (a[i - 1] === b[j - 1] ? 0 : 1),
        ),
      );
    }
    prev = row;
  }
  return prev[b.length] ?? 0;
};

/** Единственное близкое по написанию поле (опечатка в одну-две буквы); иначе `null`. */
export const nearField = (
  key: string,
  fields: readonly string[],
): string | null => {
  const limit = key.length <= 4 ? 1 : 2;
  let best: string | null = null;
  let bestDistance = limit + 1;
  let tie = false;
  for (const field of fields) {
    if (field === key) return null;
    const d = distance(key.toLowerCase(), field.toLowerCase());
    if (d < bestDistance) {
      best = field;
      bestDistance = d;
      tie = false;
    } else if (d === bestDistance) {
      tie = true;
    }
  }
  return tie ? null : best;
};

export type TextFix = {
  /** Поле в шаблоне, которого нет у версии. */
  wrong: string;
  /** На что похоже из объявленных полей. */
  right: string;
  /** Строка с первым вхождением (для подписи). */
  line: number | null;
  /** Текст файла после исправления. */
  apply: (text: string) => string;
};

const META_KEY = /project\.meta\.([A-Za-z_][\w]*)/;
const escapeRe = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Автоисправление есть у одного вида замечаний: шаблон читает `project.meta.<поле>`, а такого
 * поля у версии нет, и среди объявленных есть единственное похожее (опечатка). Сервер подсказки не
 * присылает, поэтому поле берётся из текста замечания, а похожее из подсказок редактора.
 */
export const suggestFix = (
  finding: PackDiagnostic,
  text: string,
  declared: readonly string[],
): TextFix | null => {
  const wrong = META_KEY.exec(finding.message)?.[1];
  if (!wrong) return null;
  const right = nearField(wrong, declared);
  if (!right) return null;
  const pattern = new RegExp(`(meta\\.)${escapeRe(wrong)}(?![\\w])`, "g");
  const index = text.search(pattern);
  if (index < 0) return null;
  return {
    wrong,
    right,
    line: text.slice(0, index).split("\n").length,
    apply: (source) => source.replace(pattern, `$1${right}`),
  };
};
