import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";

// Область «Подробности» (S7): правая колонка «Результата». Тяжёлое грузится лениво, сам файл
// читается сразу при входе в пространство.
const DetailsPanel = lazy(() => import("./DetailsPanel"));

export const slots = defineSpaceSlots({
  details: { result: DetailsPanel },
});
