// Отправка в панели «Изменения» (pack-studio-ux.md, 5.6): последовательность на клиенте, потому
// что у сервера для неё три разных эндпоинта. Заметки записываются в версию, затем (по галочке)
// версия выпускается, затем коммит несохранённого, отправка ветки и открытие запроса. Каждый шаг
// идемпотентен до слияния, поэтому оборванную отправку можно повторить с того же места, а
// выполненные шаги не повторяются. Файл чистый: без React и без запросов, шаги подаёт вызывающий.

export type SubmitStep = "notes" | "release" | "send";

export const SUBMIT_STEPS: readonly SubmitStep[] = [
  "notes",
  "release",
  "send",
] as const;

/** Что делать: «заметки» только если они ещё не записаны, «выпуск» по галочке, «отправка» всегда. */
export const planSteps = (input: {
  notesPending: boolean;
  release: boolean;
}): SubmitStep[] => [
  ...(input.notesPending ? (["notes"] as const) : []),
  ...(input.release ? (["release"] as const) : []),
  "send",
];

export type StepOps<R> = {
  notes: () => Promise<unknown>;
  release: () => Promise<unknown>;
  send: () => Promise<R>;
};

export type RunOutcome<R> =
  | { ok: true; done: SubmitStep[]; result: R }
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
      else await ops[step]();
    } catch (error) {
      return { ok: false, done: finished, step, error };
    }
    finished.push(step);
  }
  // `send` в плане всегда последний и всегда выполняется: результат есть.
  return { ok: true, done: finished, result: result as R };
};
