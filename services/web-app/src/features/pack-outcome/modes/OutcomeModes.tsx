import { AtlasMode } from "./AtlasMode";
import { CompareMode } from "./CompareMode";
import { MatrixMode } from "./MatrixMode";
import "./modes.css";

type OutcomeModesProps = {
  view: "matrix" | "atlas" | "compare";
};

/**
 * Режимы центра экрана «Результат» (срез F9): «Матрица», «Атлас», «Сравнить». Лежат в своём чанке
 * (`modes/index.ts`), потому что открывают их реже, чем сам результат.
 */
export const OutcomeModes = ({ view }: OutcomeModesProps) => {
  if (view === "matrix") return <MatrixMode />;
  if (view === "atlas") return <AtlasMode />;
  return <CompareMode />;
};
