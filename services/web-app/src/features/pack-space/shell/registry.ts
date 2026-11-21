import { mergeSpaceSlots, type SpaceSlots } from "./spaceSlots";

// Слоты всех областей: каждый файл `features/pack-space/<область>/slots.tsx` экспортирует
// `slots` (см. `defineSpaceSlots`). Область без этого файла ничего не кладёт в каркас.
// Тяжёлое подключайте через `lazy()`: файл читается сразу, при первом входе в пространство.
const modules = import.meta.glob<{ slots: SpaceSlots }>("../*/slots.tsx", {
  eager: true,
});

export const spaceSlots: SpaceSlots = mergeSpaceSlots(
  Object.entries(modules).map(([path, mod]) => [path, mod.slots] as const),
);
