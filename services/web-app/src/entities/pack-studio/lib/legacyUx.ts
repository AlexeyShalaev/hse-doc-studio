// В 0.38.0 новый интерфейс Студии шаблонов включался флагом: `?ux=2` (`?ux=1` возвращал прежний),
// выбор помнился в `localStorage` под ключом `ps.ux`. С 0.39.0 интерфейс один, флага нет:
// параметр из старых ссылок и закладок убирается из адреса, память браузера стирается.

const LEGACY_UX_KEY = "ps.ux";

/** Стереть память прежнего флага. Тихо: без хранилища (частное окно) стирать нечего. */
export const forgetLegacyUxFlag = (): void => {
  try {
    window.localStorage.removeItem(LEGACY_UX_KEY);
  } catch {
    // нечего стирать
  }
};

/**
 * Query без параметра `ux` (со знаком вопроса или пустая строка); `null`, если убирать нечего.
 * Остальные параметры и их порядок не меняются.
 */
export const withoutUxParam = (search: string): string | null => {
  const params = new URLSearchParams(search);
  if (!params.has("ux")) return null;
  params.delete("ux");
  const rest = params.toString();
  return rest ? `?${rest}` : "";
};
