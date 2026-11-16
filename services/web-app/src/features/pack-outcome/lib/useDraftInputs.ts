import { useCallback, useEffect, useRef, useState } from "react";
import { sameInputs } from "./inputs";

/** Пауза между последним выбором и записью в адрес (дизайн, раздел 3.3). */
export const INPUTS_DEBOUNCE_MS = 250;

type Draft = {
  /** Состояние адреса, на котором набран черновик; сменился адрес, черновик устарел. */
  at: string;
  value: Record<string, string>;
};

export type DraftInputs = {
  /** Что показывать в контролах: черновик, пока он не записан, иначе значения из адреса. */
  value: Record<string, string>;
  /** Выбор сделан, но ещё не записан в адрес (идёт пауза или ждём кнопку «Показать»). */
  pending: boolean;
  /** Изменить черновик; `now` записывает в адрес сразу, иначе по паузе. */
  set: (next: Record<string, string>, now?: boolean) => void;
  /** Записать черновик в адрес сейчас (кнопка «Показать»). */
  flush: () => void;
  /** Забыть черновик и отменить запись по паузе (сброс всего). */
  discard: () => void;
};

type Options = {
  /** Вводные из адреса. */
  source: Record<string, string>;
  /** Ключ состояния адреса: при его смене черновик отбрасывается. */
  at: string;
  commit: (next: Record<string, string>) => void;
  /** `false`: запись только по `flush` (нижний лист на телефоне). */
  auto: boolean;
  delay?: number;
};

/**
 * Черновик вводных с записью в адрес по паузе. Контролы живут от черновика, поэтому выбор виден
 * сразу, а остальной экран и запрос расчёта меняются один раз после паузы. Черновик хранит
 * состояние адреса, на котором набран: когда адрес сменился снаружи (другой сценарий, «Назад»),
 * черновик молча устаревает без эффектов и сбросов состояния. Незаписанный выбор при закрытии
 * панели записывается, а не теряется.
 */
export const useDraftInputs = ({
  source,
  at,
  commit,
  auto,
  delay = INPUTS_DEBOUNCE_MS,
}: Options): DraftInputs => {
  const [draft, setDraft] = useState<Draft | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef({ commit, at, auto });
  useEffect(() => {
    latest.current = { commit, at, auto };
  });
  /** Последний выбор: его пишут по паузе, по «Показать» и при закрытии панели. */
  const last = useRef<Draft | null>(null);

  const clear = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const write = useCallback(
    (value: Record<string, string>, base: string) => {
      clear();
      // Адрес сменился, пока шла пауза: черновик устарел, писать его поверх нового нельзя.
      if (latest.current.at !== base) return;
      latest.current.commit(value);
    },
    [clear],
  );

  const set = useCallback(
    (next: Record<string, string>, now = false) => {
      const base = latest.current.at;
      last.current = { at: base, value: next };
      setDraft(last.current);
      clear();
      if (now && latest.current.auto) write(next, base);
      else if (latest.current.auto) {
        timer.current = setTimeout(() => {
          write(next, base);
        }, delay);
      }
    },
    [clear, delay, write],
  );

  const flush = useCallback(() => {
    const current = last.current;
    if (current) write(current.value, current.at);
  }, [write]);

  const discard = useCallback(() => {
    clear();
    last.current = null;
    setDraft(null);
  }, [clear]);

  useEffect(
    () => () => {
      if (timer.current === null) return;
      const current = last.current;
      clear();
      if (current) write(current.value, current.at);
    },
    [clear, write],
  );

  const active = draft !== null && draft.at === at ? draft.value : null;
  return {
    value: active ?? source,
    pending: active !== null && !sameInputs(active, source),
    set,
    flush,
    discard,
  };
};
