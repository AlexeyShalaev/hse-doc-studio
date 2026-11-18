import { useOutcomeModel } from "../model";

/** Записать значение одной вводной в адрес (запись истории), результат пересчитается. */
export type ApplyInput = (input: string, value: string) => void;

/**
 * «Показать эти вводные» и «Что если»: одна вводная в адрес, остальные не трогаются. Умолчание
 * версии отдельно не пишется, но поверх сценария его нужно закрепить.
 */
export const useApplyInput = (): ApplyInput => {
  const { url, inputs } = useOutcomeModel();
  return (input, value) => {
    const fallback = inputs.data?.inputs.find((i) => i.id === input)?.default;
    const rest = Object.fromEntries(
      Object.entries(url.state.inputs).filter(([key]) => key !== input),
    );
    const same = url.state.scenario === null && fallback === value;
    url.update({ inputs: same ? rest : { ...rest, [input]: value } }, true);
  };
};

/**
 * Вернуть вводную в то значение адреса, что было до «Что если»: `previous` это значение из адреса
 * (его могло не быть, тогда запись снимается и действует умолчание или сценарий).
 */
export const useRestoreInput = (): ((
  input: string,
  previous: string | undefined,
) => void) => {
  const { url } = useOutcomeModel();
  return (input, previous) => {
    const rest = Object.fromEntries(
      Object.entries(url.state.inputs).filter(([key]) => key !== input),
    );
    url.update(
      {
        inputs: previous === undefined ? rest : { ...rest, [input]: previous },
      },
      true,
    );
  };
};

/**
 * Вводные адреса после «Показать комбинацию»: значения свидетеля (строки атласа из находки или
 * покрытия) ложатся поверх нынешних, остальное не трогается. Вводная, которой нет в версии, не
 * пишется (сервер отклонил бы весь запрос); умолчание без сценария отдельно не пишется.
 */
export const useWitnessInputs = (): ((
  values: Readonly<Record<string, string>>,
) => Record<string, string>) => {
  const { url, inputs } = useOutcomeModel();
  return (values) => {
    const known = inputs.data
      ? new Map(inputs.data.inputs.map((item) => [item.id, item.default]))
      : null;
    const next = new Map(Object.entries(url.state.inputs));
    for (const [input, value] of Object.entries(values)) {
      if (known && !known.has(input)) continue;
      if (url.state.scenario === null && known?.get(input) === value) {
        next.delete(input);
      } else next.set(input, value);
    }
    return Object.fromEntries(next);
  };
};
