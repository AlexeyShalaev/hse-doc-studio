import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";

// Центр и левая колонка вкладки «Результат» (срез S6). Тяжёлое грузится лениво: сам файл читается
// сразу, при первом входе в пространство.
const ResultNav = lazy(() => import("./ResultNav"));
const ResultMain = lazy(() => import("./ResultMain"));

export const slots = defineSpaceSlots({
  nav: { result: ResultNav },
  main: { result: ResultMain },
});
