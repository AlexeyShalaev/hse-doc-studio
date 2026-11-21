// Последнее изменение условий: что было, что стало и как назвать. Лежит вне React, потому что
// плашка «что изменилось» живёт в полосе над результатом, а подсветку строк читает центр
// (`useSituationDelta`); общий источник один. Это память только на время сеанса.

export type SituationSnapshot = {
  inputs: Record<string, string>;
  caseId: string | null;
};

export type DeltaRecord = {
  /** Пространство, пак, шаблон и версия: чужую запись другой версии не показываем. */
  scope: string;
  before: SituationSnapshot;
  after: SituationSnapshot;
  /** Что сделал человек словами: «Работа под NDA: Да». */
  label: string;
  /** Номер записи: меняется с каждым новым изменением. */
  seq: number;
  /** Строки подсвечены (несколько секунд после изменения). */
  highlight: boolean;
  dismissed: boolean;
};

export const HIGHLIGHT_MS = 6000;

let current: DeltaRecord | null = null;
let seq = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

const emit = () => {
  listeners.forEach((listener) => {
    listener();
  });
};

const stopTimer = () => {
  if (timer !== null) clearTimeout(timer);
  timer = null;
};

export const deltaStore = {
  get: (): DeltaRecord | null => current,
  subscribe: (listener: () => void): (() => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  record: (
    next: Pick<DeltaRecord, "scope" | "before" | "after" | "label">,
  ): void => {
    stopTimer();
    seq += 1;
    current = { ...next, seq, highlight: true, dismissed: false };
    const mine = seq;
    timer = setTimeout(() => {
      if (current?.seq === mine) {
        current = { ...current, highlight: false };
        emit();
      }
    }, HIGHLIGHT_MS);
    emit();
  },
  dismiss: (): void => {
    if (!current) return;
    stopTimer();
    current = { ...current, dismissed: true, highlight: false };
    emit();
  },
  /** Для тестов: забыть всё. */
  reset: (): void => {
    stopTimer();
    current = null;
    emit();
  },
};
