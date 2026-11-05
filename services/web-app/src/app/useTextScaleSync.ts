import { useEffect, useRef, useState } from "react";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { isTextScale, useThemeStore } from "@shared/lib";

const RETRY_MS = 3000;

// Размер текста лежит на аккаунте (настройка text_scale) и в localStorage: из
// localStorage страница красится без мигания, аккаунт переносит выбор на другое
// устройство.
//  - Пока человек на этом устройстве ничего не выбирал (textScaleChosen), берём
//    значение аккаунта.
//  - Явный выбор всегда побеждает: он остаётся на устройстве, пока PUT идёт или
//    не удался, и уходит на аккаунт, а при ошибке повторяется.
export const useTextScaleSync = (enabled: boolean): void => {
  const settings = useAppSettings({ enabled });
  const { mutateAsync } = useUpdateAppSettings();
  const remote = settings.data?.text_scale;
  const textScale = useThemeStore((s) => s.textScale);
  const chosen = useThemeStore((s) => s.textScaleChosen);
  const adoptTextScale = useThemeStore((s) => s.adoptTextScale);
  const inFlight = useRef<number | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (chosen || !isTextScale(remote) || remote === textScale) return;
    adoptTextScale(remote);
  }, [chosen, remote, textScale, adoptTextScale]);

  useEffect(() => {
    if (!enabled || !chosen || !isTextScale(remote) || remote === textScale) {
      return;
    }
    if (inFlight.current === textScale) return;
    const sent = textScale;
    inFlight.current = sent;
    let timer: ReturnType<typeof setTimeout> | undefined;
    mutateAsync({ text_scale: sent })
      .then(() => {
        inFlight.current = null;
        setTick((n) => n + 1);
      })
      .catch(() => {
        timer = setTimeout(() => {
          inFlight.current = null;
          setTick((n) => n + 1);
        }, RETRY_MS);
      });
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [enabled, chosen, remote, textScale, tick, mutateAsync]);
};
