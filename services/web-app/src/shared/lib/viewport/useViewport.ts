import {
  COARSE_POINTER_QUERY,
  COMPACT_QUERY,
  DRAWER_QUERY,
  PHONE_QUERY,
  TABLET_QUERY,
  type ViewportClass,
} from "./breakpoints";
import { useMediaQuery } from "./useMediaQuery";

/** Ширина телефона (до 767.98 px). Верный с первого кадра, без мигания. */
export const useIsPhoneWidth = (): boolean => useMediaQuery(PHONE_QUERY);

/** Ширина планшета (768 – 1023.98 px). */
export const useIsTabletWidth = (): boolean => useMediaQuery(TABLET_QUERY);

/** Уже десктопа: телефон или планшет. */
export const useIsCompactWidth = (): boolean => useMediaQuery(COMPACT_QUERY);

/** Основной указатель - палец. Нужен там, где поведение зависит от касания, а не от ширины. */
export const useIsCoarsePointer = (): boolean =>
  useMediaQuery(COARSE_POINTER_QUERY);

/** Класс окна одним значением: удобно для switch. */
export const useViewportClass = (): ViewportClass => {
  const isPhone = useIsPhoneWidth();
  const isTablet = useIsTabletWidth();
  if (isPhone) return "phone";
  return isTablet ? "tablet" : "desktop";
};

/** Рабочее место проекта с выдвижной панелью (до 820 px). */
export const useIsDrawerWidth = (): boolean => useMediaQuery(DRAWER_QUERY);
