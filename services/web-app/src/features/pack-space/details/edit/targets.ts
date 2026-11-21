import type { OutcomeTrace } from "@entities/pack-studio";
import { ruleKey } from "@features/pack-outcome/lib/rules";
import {
  isEditableShape,
  shapeOf,
} from "@features/pack-outcome/lib/edit/shape";
import type { EditTarget } from "./useConditionEdit";

/**
 * Какие условия элемента можно поправить по месту: записи описания версии, у которых есть
 * мини-форма. Одно и то же правило в нескольких решениях цепочки встречается один раз.
 * `other`: сколько правил править здесь нельзя (зашиты в Студию или правятся только в
 * «Содержимом»).
 */
export const editTargets = (
  chain: readonly OutcomeTrace[],
): { targets: EditTarget[]; other: number } => {
  const seen = new Set<string>();
  const targets: EditTarget[] = [];
  let other = 0;
  for (const trace of chain) {
    const key = ruleKey(trace.rule);
    if (seen.has(key)) continue;
    seen.add(key);
    const { rule } = trace;
    const shape =
      rule.origin === "manifest" ? shapeOf(rule.pointer ?? "") : null;
    if (rule.origin === "manifest" && shape && isEditableShape(shape)) {
      targets.push({
        file: rule.file ?? "",
        pointer: rule.pointer ?? "",
        shape,
        kind: trace.kind,
      });
    } else {
      other += 1;
    }
  }
  return { targets, other };
};
