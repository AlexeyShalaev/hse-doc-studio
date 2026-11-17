import { lazy, Suspense } from "react";
import { useRuleEdit } from "./context";

const LazyEditBar = lazy(() =>
  import("./EditPanels").then((m) => ({ default: m.EditBar })),
);

export const LazyRuleEditor = lazy(() =>
  import("./EditPanels").then((m) => ({ default: m.RuleEditor })),
);

/**
 * Полоса правок над панелью: чанк с ней грузится, только когда есть что показать (правка внесена,
 * пришло сравнение или отказ), и нет ни одной строки в ленте до этого.
 */
export const EditBarSlot = () => {
  const ui = useRuleEdit();
  if (!ui?.available) return null;
  const notice = ui.notice?.source === "history";
  if (ui.history.entries.length === 0 && !ui.delta && !notice) return null;
  return (
    <Suspense fallback={null}>
      <LazyEditBar />
    </Suspense>
  );
};
