import { createContext, type ReactNode } from "react";

/** Вкладки страницы с несколькими видами (раннеры и очередь): встают под заголовок вида. */
export const HeaderTabsContext = createContext<ReactNode>(null);
