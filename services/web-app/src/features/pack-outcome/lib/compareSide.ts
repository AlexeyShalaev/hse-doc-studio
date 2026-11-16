import { OutcomeStateSchema, type OutcomeState } from "@entities/pack-studio";

// Сторона сравнения режима «Сравнить» (template-studio-outcome.md, раздел 3.6) и её запись в адресе:
//   ?view=compare&left=scenario:company-supervisor&right=screen@head
// Сторона это источник вводных и состояние версии, из которого они считаются. Клиент условий не
// считает: обе стороны уходят серверу как `OutcomeSubject`, он же отдаёт список изменений.

/** Откуда берутся вводные стороны. */
export type CompareSource =
  /** Вводные экрана: сценарий, изменения поверх него и набор данных, как в левой панели. */
  | { kind: "screen" }
  /** Умолчания версии без сценария. */
  | { kind: "defaults" }
  | { kind: "scenario"; id: string }
  /** Свои вводные, зафиксированные кнопкой «Зафиксировать вводные экрана». */
  | { kind: "inputs"; inputs: Record<string, string> };

export type CompareSide = {
  source: CompareSource;
  /** Состояние версии; `null`: то, что выбрано на экране. */
  state: OutcomeState | null;
};

const SCENARIO = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const INPUT_KEY = /^[a-z][a-z0-9_.-]{0,63}$/;
const CONTROL = /\p{Cc}/u;
const MAX_FROZEN = 64;
const MAX_VALUE = 128;

/** Запись стороны: `screen`, `defaults`, `scenario:<id>`, `inputs:<k=v&k=v>`; `@<состояние>` в конце. */
export const formatSide = (side: CompareSide): string => {
  const { source } = side;
  const text =
    source.kind === "scenario"
      ? `scenario:${source.id}`
      : source.kind === "inputs"
        ? `inputs:${new URLSearchParams(
            Object.entries(source.inputs).sort(([a], [b]) =>
              a < b ? -1 : a > b ? 1 : 0,
            ),
          ).toString()}`
        : source.kind;
  return side.state === null ? text : `${text}@${side.state}`;
};

const parseInputs = (raw: string): Record<string, string> | null => {
  const inputs: Record<string, string> = {};
  let count = 0;
  for (const [key, value] of new URLSearchParams(raw)) {
    if (
      !INPUT_KEY.test(key) ||
      value === "" ||
      value.length > MAX_VALUE ||
      CONTROL.test(value) ||
      key in inputs ||
      count >= MAX_FROZEN
    ) {
      return null;
    }
    inputs[key] = value;
    count += 1;
  }
  return inputs;
};

/** Разбор стороны из адреса: непонятное даёт `null` (экран возьмёт сторону по умолчанию). */
export const parseSide = (raw: string | null): CompareSide | null => {
  if (!raw) return null;
  let text = raw;
  let state: OutcomeState | null = null;
  const at = raw.lastIndexOf("@");
  if (at > 0) {
    const parsed = OutcomeStateSchema.safeParse(raw.slice(at + 1));
    if (parsed.success) {
      state = parsed.data;
      text = raw.slice(0, at);
    }
  }
  if (text === "screen" || text === "defaults") {
    return { source: { kind: text }, state };
  }
  if (text.startsWith("scenario:")) {
    const id = text.slice("scenario:".length);
    return SCENARIO.test(id)
      ? { source: { kind: "scenario", id }, state }
      : null;
  }
  if (text.startsWith("inputs:")) {
    const inputs = parseInputs(text.slice("inputs:".length));
    return inputs ? { source: { kind: "inputs", inputs }, state } : null;
  }
  return null;
};

export const sameSide = (a: CompareSide, b: CompareSide): boolean =>
  formatSide(a) === formatSide(b);
