import type { ComponentType } from "react";
import type { SpaceTab } from "@entities/pack-studio";

// Слоты каркаса (pack-studio-ux.md, 8.6). Область кладёт свои компоненты в `slots.tsx` рядом с
// собой, каркас собирает их сам (`registry.ts`): общие файлы при этом не правятся.
// Слот-компонент не получает props: место и адрес он берёт из `useSpace()` и `useSpaceNav()`.

/** Компонент слота для каждой вкладки отдельно. */
export type SpaceTabSlot = Partial<Record<SpaceTab, ComponentType>>;

export type SpaceSlots = {
  /** Левая часть верхней полосы: назад, название, меню «Ещё» пространства (S2). */
  header?: ComponentType;
  /** Кнопка «Изменения» с числом, правая часть верхней полосы (S3). */
  changesButton?: ComponentType;
  /** Главная кнопка следующего шага, правее «Изменений» (S4). */
  nextStep?: ComponentType;
  /** Вторая полоса: крошки Пак, Шаблон, Версия и вкладки (S2). Заменяет вкладки каркаса. */
  contextBar?: ComponentType;
  /** Панель «Изменения»: справа вместо «Подробностей», на телефоне страница (S3). */
  changes?: ComponentType;
  /** Нижние вкладки телефона (S11). Заменяют вкладки каркаса. */
  bottomTabs?: ComponentType;
  /** Левая колонка «что»: части результата, что редактируем. */
  nav?: SpaceTabSlot;
  /** Полоса над центром: «Для какого студента» (S5). */
  mainTop?: SpaceTabSlot;
  /** Центр: то, на что смотрим. */
  main?: SpaceTabSlot;
  /** Правая колонка «подробности»: почему так, предпросмотр. */
  details?: SpaceTabSlot;
};

type Scalar = Exclude<keyof SpaceSlots, "nav" | "mainTop" | "main" | "details">;
const SCALAR: Scalar[] = [
  "header",
  "changesButton",
  "nextStep",
  "contextBar",
  "changes",
  "bottomTabs",
];
const PER_TAB = ["nav", "mainTop", "main", "details"] as const;

/** Типизирует `export const slots = defineSpaceSlots({...})` в `slots.tsx` области. */
export const defineSpaceSlots = (slots: SpaceSlots): SpaceSlots => slots;

/**
 * Склейка слотов областей. Слот занимает одна область: второй претендент это ошибка, и она
 * называет оба файла, а не молча затирает чужое.
 */
export const mergeSpaceSlots = (
  sources: readonly (readonly [source: string, slots: SpaceSlots])[],
): SpaceSlots => {
  const out: SpaceSlots = {};
  const owner = new Map<string, string>();
  const claim = (id: string, source: string) => {
    const prev = owner.get(id);
    if (prev) throw new Error(`Слот «${id}» занят: ${prev} и ${source}`);
    owner.set(id, source);
  };
  for (const [source, slots] of sources) {
    for (const name of SCALAR) {
      const component = slots[name];
      if (!component) continue;
      claim(name, source);
      out[name] = component;
    }
    for (const name of PER_TAB) {
      for (const [tab, component] of Object.entries(slots[name] ?? {})) {
        claim(`${name}.${tab}`, source);
        out[name] = { ...out[name], [tab]: component };
      }
    }
  }
  return out;
};
