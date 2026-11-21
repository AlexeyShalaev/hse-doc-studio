import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";

// Область «Предпросмотр PDF» (S9): правая колонка «Содержимого». В «Результате» та же панель
// открывается внутри «Подробностей» (S7) по параметру `preview=1`. Тяжёлое грузится лениво.
const ContentPreview = lazy(() => import("./ContentPreview"));

export const slots = defineSpaceSlots({
  details: { content: ContentPreview },
});
