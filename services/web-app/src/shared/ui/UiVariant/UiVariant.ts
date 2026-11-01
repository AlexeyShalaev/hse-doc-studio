import { createContext, useContext } from "react";

/**
 * Вид общих блоков в поддереве. studio: рабочее место с моноширинными
 * подсказками и мелкими подписями полей. console: консоли вроде админки, где
 * весь текст набран обычным шрифтом, а поля оформлены как строки настроек.
 * Контекст доходит и до порталов (окна, подсказки), куда CSS-предок не достаёт.
 */
export type UiVariant = "studio" | "console";

export const UiVariantContext = createContext<UiVariant>("studio");

export const useUiVariant = (): UiVariant => useContext(UiVariantContext);
