import type { OutcomeElementRef, PackOutcome } from "@entities/pack-studio";
import { isUnder } from "./shape";

/**
 * Элементы результата, о которых говорят решения по записи манифеста (сама запись или вложенная
 * в неё): число для сводки «что изменится» перед разрушающим действием. Данные это трасса
 * показанного результата, то есть текущая комбинация вводных: другие комбинации сервер не
 * считал, и экран об этом пишет. `null`, пока результата нет.
 */
export const affectedElements = (
  outcome: PackOutcome | undefined,
  file: string,
  pointer: string,
): OutcomeElementRef[] | null => {
  if (!outcome) return null;
  const seen = new Map<string, OutcomeElementRef>();
  for (const decision of outcome.trace) {
    const rule = decision.rule;
    if (rule.origin !== "manifest" || rule.file !== file) continue;
    if (rule.pointer === null || !isUnder(rule.pointer, pointer)) continue;
    for (const subject of decision.subjects) {
      seen.set(`${subject.section}:${subject.id}`, subject);
    }
  }
  return [...seen.values()];
};
