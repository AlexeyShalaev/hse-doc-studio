import type { OutcomeInput } from "@entities/pack-studio";

// Какие условия показать кнопками (pack-studio-ux.md, 5.3): три самых влиятельных. Влияние это
// число правил, которые условие читают (`rules`); условия с пустым `affects` ничего не меняют
// и в этот отбор не попадают: они лежат в конце окна «Ещё условий».

/** Условие ничего не меняет в результате шаблона. */
export const isInert = (input: OutcomeInput): boolean =>
  input.affects.length === 0;

/** Не больше `count` условий, которые читает больше всего правил; при равенстве порядок версии. */
export const topInputs = (
  inputs: readonly OutcomeInput[],
  count = 3,
): OutcomeInput[] =>
  inputs
    .map((input, order) => ({ input, order }))
    .filter(({ input }) => !isInert(input))
    .sort((a, b) => b.input.rules - a.input.rules || a.order - b.order)
    .slice(0, count)
    .map(({ input }) => input);

export type InputGroups = {
  /** На полосе: три главных и те, что человек уже изменил (в том числе в окне). */
  shown: OutcomeInput[];
  /** В окне «Ещё условий»: все остальные, которые что-то меняют (изменённые тоже). */
  more: OutcomeInput[];
  /** В конце окна: «Не влияют на этот шаблон». */
  inert: OutcomeInput[];
};

/**
 * Раскладка условий по полосе и окну; порядок внутри групп как в версии. Состав окна не зависит
 * от того, что изменено: строки в нём не прыгают, пока человек меняет значения.
 */
export const groupInputs = (
  inputs: readonly OutcomeInput[],
  changed: ReadonlySet<string>,
  count = 3,
): InputGroups => {
  const top = new Set(topInputs(inputs, count).map((input) => input.id));
  return {
    shown: inputs.filter(
      (input) =>
        top.has(input.id) || (changed.has(input.id) && !isInert(input)),
    ),
    more: inputs.filter((input) => !top.has(input.id) && !isInert(input)),
    inert: inputs.filter(isInert),
  };
};
