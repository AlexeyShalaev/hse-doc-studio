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
