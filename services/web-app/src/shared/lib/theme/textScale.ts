// Размер текста интерфейса: ступени в процентах от обычного. Корень страницы
// получает `font-size: 16px * --text-scale` (index.css), а всё, что в rem,
// растёт вместе с ним: шрифты, отступы, высоты, иконки. Те же числа проверяет
// бэкенд (use_cases/settings/value_rules.py) и загрузочный скрипт index.html.
export const TEXT_SCALE_STEPS = [90, 100, 112, 125, 140] as const;
export type TextScale = (typeof TEXT_SCALE_STEPS)[number];

export const DEFAULT_TEXT_SCALE: TextScale = 100;

export const isTextScale = (value: unknown): value is TextScale =>
  TEXT_SCALE_STEPS.some((step) => step === value);

// Негодное значение (чужой localStorage, старый бэкенд) читается как обычный размер.
export const normalizeTextScale = (value: unknown): TextScale =>
  isTextScale(value) ? value : DEFAULT_TEXT_SCALE;

export const applyTextScale = (root: HTMLElement, scale: TextScale): void => {
  root.style.setProperty("--text-scale", String(scale / 100));
  root.setAttribute("data-text-scale", String(scale));
};
