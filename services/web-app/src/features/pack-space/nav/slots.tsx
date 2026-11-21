import { defineSpaceSlots } from "../shell/spaceSlots";
import { ContextBar } from "./ContextBar";
import { SpaceBar } from "./SpaceBar";

// Область nav (срез S2): верхняя полоса пространства и полоса «что смотрю» с вкладками. Слоты
// `changesButton` и `nextStep` в полосе принадлежат S3 и S4.
export const slots = defineSpaceSlots({
  header: SpaceBar,
  contextBar: ContextBar,
});
