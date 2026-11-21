import { defineSpaceSlots } from "../shell/spaceSlots";
import { NextStepButton } from "./NextStepButton";

// Область «Главная кнопка» (S4): одна кнопка следующего шага правее «Изменений». Она живая всегда
// (подпись зависит от статуса изменений), поэтому не ленивая; окна, которые она открывает, грузятся
// по требованию. Раздел отправки внутри панели «Изменения» тоже этой области: его подключает
// `changes/ChangesDrawer`, и он едет в чанке панели.
export const slots = defineSpaceSlots({ nextStep: NextStepButton });
