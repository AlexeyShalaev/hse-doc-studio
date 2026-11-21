import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";

// Область «Содержимое» (S8a): навигация «Что редактируем» и центр. Слот `details.content`
// (предпросмотр PDF) занимает S9. Продолжение S8b - S8d подключается файлами-расширениями в
// `extend/`, этот файл они не трогают (docs/design/pack-studio-ux.md, 12.7).
const ContentNav = lazy(() => import("./ContentNav"));
const ContentMain = lazy(() => import("./ContentMain"));

export const slots = defineSpaceSlots({
  nav: { content: ContentNav },
  main: { content: ContentMain },
});
