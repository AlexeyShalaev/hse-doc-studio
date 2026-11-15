// Порядок маршрута пака (signing-route.md, 5.2): шаги из id слотов каталога, внутри шага
// параллельно. Те же действия, что у маршрута проекта (features/signing-route-editor), но
// без людей: слот переносится между шагами, шаги переставляются, опустевший шаг исчезает.

export type Steps = string[][];

type Position = { step: number; index: number };

const locate = (steps: Steps, slot: string): Position | null => {
  for (const [step, slots] of steps.entries()) {
    const index = slots.indexOf(slot);
    if (index !== -1) return { step, index };
  }
  return null;
};

/**
 * Перенести слот: в существующий шаг (`newStep: false`) или отдельным шагом на место
 * `step` (`newStep: true`, 0..число шагов). Опустевший шаг исчезает.
 */
export const moveSlot = (
  steps: Steps,
  slot: string,
  target: { step: number; newStep: boolean },
): Steps => {
  const from = locate(steps, slot);
  if (!from) return steps;
  if (!target.newStep && target.step === from.step) return steps;
  const without = steps.map((slots, i) =>
    i === from.step ? slots.filter((_, j) => j !== from.index) : slots,
  );
  const emptied = without[from.step]?.length === 0;
  const rest = emptied ? without.filter((_, i) => i !== from.step) : without;
  const at = emptied && from.step < target.step ? target.step - 1 : target.step;
  if (target.newStep) return [...rest.slice(0, at), [slot], ...rest.slice(at)];
  return rest.map((slots, i) => (i === at ? [...slots, slot] : slots));
};

/** «В один шаг с предыдущим». */
export const joinPrevious = (steps: Steps, slot: string): Steps => {
  const from = locate(steps, slot);
  if (!from || from.step === 0) return steps;
  return moveSlot(steps, slot, { step: from.step - 1, newStep: false });
};

/** «Отдельным шагом»: сразу после своего шага. */
export const separate = (steps: Steps, slot: string): Steps => {
  const from = locate(steps, slot);
  if (!from || (steps[from.step]?.length ?? 0) < 2) return steps;
  return moveSlot(steps, slot, { step: from.step + 1, newStep: true });
};

/** Переставить шаг `from` на место `to` (индексы до перестановки). */
export const moveStep = (steps: Steps, from: number, to: number): Steps => {
  const moved = steps[from];
  if (!moved || from === to || to < 0 || to >= steps.length) return steps;
  const rest = steps.filter((_, i) => i !== from);
  return [...rest.slice(0, to), moved, ...rest.slice(to)];
};

export const removeSlot = (steps: Steps, slot: string): Steps =>
  steps
    .map((slots) => slots.filter((s) => s !== slot))
    .filter((slots) => slots.length > 0);

/** Слот отдельным последним шагом (если его ещё нет в порядке). */
export const addSlot = (steps: Steps, slot: string): Steps =>
  locate(steps, slot) ? steps : [...steps, [slot]];

/**
 * Порядок, с которого начинается своя правка: встроенный порядок только из слотов
 * каталога, как его читает `route_order` (неизвестные id выпадают, повторы тоже).
 */
export const seedSteps = (steps: Steps, catalog: readonly string[]): Steps => {
  const known = new Set(catalog);
  const seen = new Set<string>();
  return steps
    .map((step) =>
      step.filter((slot) => {
        if (!known.has(slot) || seen.has(slot)) return false;
        seen.add(slot);
        return true;
      }),
    )
    .filter((step) => step.length > 0);
};

/** Слоты каталога, которых нет в порядке: они пойдут последними шагами в порядке каталога. */
export const missingSlots = (
  steps: Steps,
  catalog: readonly string[],
): string[] => {
  const placed = new Set(steps.flat());
  return catalog.filter((slot) => !placed.has(slot));
};

export const sameSteps = (a: Steps, b: Steps): boolean =>
  JSON.stringify(a) === JSON.stringify(b);

/** Шаги словами: «1. Автор; 2. Научный руководитель, Консультант». */
export const stepsText = (
  steps: Steps,
  slotLabel: (slot: string) => string,
): string =>
  steps
    .map((step, i) => `${String(i + 1)}. ${step.map(slotLabel).join(", ")}`)
    .join("; ");
