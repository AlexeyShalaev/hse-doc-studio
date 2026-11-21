import { createContext, useContext } from "react";
import { useIsPhoneWidth } from "@shared/lib";

// Телефон ли это экран пространства. Раскладку решает CSS по `data-phone` каркаса, а там, где
// нужна другая разметка (страница-список вместо левой колонки), областям нужен ответ в JS. Его
// даёт хост (`SpaceScreen phone`): рамка галереи и тесты задают телефон без ширины окна. Вне
// каркаса (редкий вызов) отвечает ширина окна, как у остального приложения.
export const SpacePhoneContext = createContext<boolean | null>(null);

export const useSpacePhone = (): boolean => {
  const hosted = useContext(SpacePhoneContext);
  const viewport = useIsPhoneWidth();
  return hosted ?? viewport;
};
