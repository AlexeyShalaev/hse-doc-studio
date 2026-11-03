import { Suspense, lazy, useCallback } from "react";
import { useHelpStore } from "@entities/help";
import { useHelpHotkey } from "../lib/useHelpHotkey";

// Панель — отдельный чанк: пока справку ни разу не открывали, ни её код, ни карта не грузятся.
const HelpPanel = lazy(() =>
  import("./HelpPanel").then((m) => ({ default: m.HelpPanel })),
);

/** Точка монтирования панели справки в корневом макете; здесь же клавиша `?` на каждом экране. */
export const HelpHost = () => {
  const everOpened = useHelpStore((s) => s.everOpened);
  const open = useHelpStore((s) => s.open);
  const openForScreen = useCallback(() => {
    open();
  }, [open]);
  useHelpHotkey(openForScreen);
  if (!everOpened) return null;
  return (
    <Suspense fallback={null}>
      <HelpPanel />
    </Suspense>
  );
};
