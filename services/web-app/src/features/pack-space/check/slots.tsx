import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";

// Вкладка «Проверка» (pack-studio-ux.md, 5.7, срез S10): слева части (замечания, типовые случаи,
// что на что влияет) и сравнение, в центре выбранная часть. Правой колонки нет: вся подробность
// лежит в самой части. Тяжёлое грузится отдельным чанком, только когда вкладку открыли.
const CheckNav = lazy(() => import("./CheckNav"));
const CheckMain = lazy(() => import("./CheckMain"));

export const slots = defineSpaceSlots({
  nav: { check: CheckNav },
  main: { check: CheckMain },
});
