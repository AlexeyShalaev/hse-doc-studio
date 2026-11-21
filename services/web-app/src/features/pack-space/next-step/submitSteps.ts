// Отправка в панели «Изменения» (pack-studio-ux.md, 5.6): последовательность на клиенте, потому
// что у сервера для неё три разных эндпоинта. Заметки записываются в версию, затем, если правки
// требуют другого номера, версия переезжает на нужный номер (шаг `number`, после него ход
// приостанавливается: экран идёт за версией и продолжает уже с новым каталогом), затем (по
// галочке) версия выпускается, затем коммит несохранённого, отправка ветки и открытие запроса. Каждый шаг
// идемпотентен до слияния, поэтому оборванную отправку можно повторить с того же места, а
// выполненные шаги не повторяются. Файл чистый: без React и без запросов, шаги подаёт вызывающий.

export type SubmitStep = "notes" | "number" | "release" | "send";

export const SUBMIT_STEPS: readonly SubmitStep[] = [
  "notes",
  "number",
  "release",
  "send",
] as const;

/**
 * Что делать: «заметки» только если они ещё не записаны, «номер» если правки требуют другого
 * номера, «выпуск» по галочке, «отправка» всегда.
 */
export const planSteps = (input: {
  notesPending: boolean;
  release: boolean;
  renumber?: boolean;
}): SubmitStep[] => [
  ...(input.notesPending ? (["notes"] as const) : []),
  ...(input.renumber ? (["number"] as const) : []),
  ...(input.release ? (["release"] as const) : []),
  "send",
];

export type StepOps<R> = {
  notes: () => Promise<unknown>;
  /** Смена номера; нужна только если в плане есть шаг `number`. */
  number?: () => Promise<unknown>;
  release: () => Promise<unknown>;
  send: () => Promise<R>;
};

export type RunOutcome<R> =
  | { ok: true; done: SubmitStep[]; result: R; paused?: false }
  /** После смены номера каталог версии другой: ход остановлен, продолжать с новой версией. */
  | { ok: true; done: SubmitStep[]; paused: true; next: SubmitStep[] }
  | { ok: false; done: SubmitStep[]; step: SubmitStep; error: unknown };

/**
 * Выполняет `plan` по порядку, пропуская шаги из `done`. На первой ошибке останавливается и
 * говорит, на каком шаге; сделанное остаётся в `done`, повтор начинается с упавшего шага.
 * `onStep` сообщает, какой шаг начался (для списка «что сейчас делаем»).
 */
export const runSteps = async <R>(
  plan: readonly SubmitStep[],
  done: readonly SubmitStep[],
  ops: StepOps<R>,
  onStep?: (step: SubmitStep) => void,
): Promise<RunOutcome<R>> => {
  const finished = [...done];
  let result: R | undefined;
  for (const step of plan) {
    if (finished.includes(step)) continue;
    onStep?.(step);
    try {
      if (step === "send") result = await ops.send();
      else if (step === "number") await ops.number?.();
      else await ops[step]();
    } catch (error) {
      return { ok: false, done: finished, step, error };
    }
    finished.push(step);
    if (step === "number") {
      return {
        ok: true,
        done: finished,
        paused: true,
        next: plan.filter((item) => !finished.includes(item)),
      };
    }
  }
  // `send` в плане всегда последний и всегда выполняется: результат есть.
  return { ok: true, done: finished, result: result as R };
};
