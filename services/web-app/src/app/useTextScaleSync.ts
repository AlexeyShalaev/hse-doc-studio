import { useEffect } from "react";
import { useAppSettings } from "@entities/app-settings";
import { DEFAULT_TEXT_SCALE, isTextScale, useThemeStore } from "@shared/lib";

// Размер текста лежит на аккаунте (настройка text_scale) и в localStorage: из
// localStorage страница красится без мигания, аккаунт переносит выбор на другое
// устройство. Пока на этом устройстве выбор не менялся (обычный размер), берём
// значение аккаунта; выбранное здесь ступенью уходит на сервер из настроек.
export const useTextScaleSync = (enabled: boolean): void => {
  const settings = useAppSettings({ enabled });
  const remote = settings.data?.text_scale;
  const setTextScale = useThemeStore((s) => s.setTextScale);
  useEffect(() => {
    if (!isTextScale(remote)) return;
    if (useThemeStore.getState().textScale === DEFAULT_TEXT_SCALE) {
      setTextScale(remote);
    }
  }, [remote, setTextScale]);
};
