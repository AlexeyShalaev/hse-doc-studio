import type { OutcomeView } from "../lib/urlState";

/** Идентификаторы для связи вкладки режима и её панели (aria-controls и aria-labelledby). */
export const viewTabId = (view: OutcomeView): string => `po-view-tab-${view}`;
export const VIEW_PANEL_ID = "po-view-panel";
