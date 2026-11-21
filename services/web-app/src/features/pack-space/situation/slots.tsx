import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";

// Область «Для какого студента» (S5): полоса условий и плашка «что изменилось» над центром.
const SituationTop = lazy(() => import("./SituationTop"));

export const slots = defineSpaceSlots({
  mainTop: { result: SituationTop },
});
