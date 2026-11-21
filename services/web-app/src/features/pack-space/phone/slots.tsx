import { defineSpaceSlots } from "../shell/spaceSlots";
import { PhoneTabs } from "./PhoneTabs";

// Область «Телефон» (срез S11): нижние вкладки. Они живые всегда (число на «Изменениях» должно
// быть видно), поэтому не ленивые: компонент крошечный. Остальное для узкого экрана лежит в
// областях и в `space-phone.css` (зоны касания, шторки, прокручиваемые ряды).
export const slots = defineSpaceSlots({ bottomTabs: PhoneTabs });
