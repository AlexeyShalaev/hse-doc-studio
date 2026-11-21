import { lazy } from "react";
import { defineSpaceSlots } from "../shell/spaceSlots";
import { ChangesButton } from "./ChangesButton";

// Область «Изменения» (S3): кнопка с числом в полосе пространства и панель справа (на телефоне
// страница). Кнопка живая всегда (число должно быть видно при закрытой панели), панель грузится
// отдельным чанком и только когда открыта.
const ChangesDrawer = lazy(() => import("./ChangesDrawer"));

export const slots = defineSpaceSlots({
  changesButton: ChangesButton,
  changes: ChangesDrawer,
});
